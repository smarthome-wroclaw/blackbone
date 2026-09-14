"""Safe lifecycle management for containerised Linux extensions."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from boneio.extensions.manifest import ExtensionManifest, ExtensionType


class ExtensionRuntimeError(RuntimeError):
    """Raised when an extension cannot be safely managed."""


class ContainerExtensionRuntime:
    """Run an app extension with explicit, least-privilege Docker arguments."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def status(self, extension_id: str) -> dict:
        name = self._container_name(extension_id)
        result = self._docker("inspect", "--format", "{{json .State}}", name, check=False)
        if result.returncode:
            return {"id": extension_id, "installed": False, "running": False}
        try:
            state = json.loads(result.stdout)
        except json.JSONDecodeError:
            state = {}
        return {"id": extension_id, "installed": True, "running": state.get("Running", False), "status": state.get("Status", "unknown")}

    def start(self, manifest: ExtensionManifest, approved_permissions: set[str]) -> dict:
        if manifest.type is not ExtensionType.APP or manifest.runtime is None:
            raise ExtensionRuntimeError("Only app extensions have a container runtime")
        requested = self._requested_permissions(manifest)
        if requested != approved_permissions:
            raise ExtensionRuntimeError("Approved permissions must exactly match the extension request")
        if manifest.permissions.usb or manifest.permissions.gpio:
            raise ExtensionRuntimeError("USB and GPIO require a dedicated reviewed runtime and are not enabled yet")
        name = self._container_name(manifest.id)
        self._docker("rm", "-f", name, check=False)
        extension_data = self.data_dir / manifest.id
        extension_data.mkdir(parents=True, exist_ok=True)
        command = ["run", "-d", "--name", name, "--restart", "unless-stopped", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--mount", f"type=bind,src={extension_data},dst=/data"]
        if manifest.permissions.host_network:
            command.extend(["--network", "host"])
        elif manifest.permissions.network:
            command.extend(["--network", "bridge"])
            command.extend(port for value in manifest.runtime.ports for port in ("-p", f"{value}:{value}"))
        else:
            command.extend(["--network", "none"])
        for device in manifest.permissions.serial_devices:
            command.extend(["--device", device])
        for key, value in manifest.runtime.environment.items():
            command.extend(["--env", f"{key}={value}"])
        command.append(manifest.runtime.image)
        command.extend(manifest.runtime.command)
        self._docker(*command)
        return self.status(manifest.id)

    def stop(self, extension_id: str) -> dict:
        self._docker("stop", self._container_name(extension_id), check=False)
        return self.status(extension_id)

    def logs(self, extension_id: str, tail: int = 200) -> str:
        return self._docker("logs", "--tail", str(max(1, min(tail, 1000))), self._container_name(extension_id), check=False).stdout

    @staticmethod
    def _requested_permissions(manifest: ExtensionManifest) -> set[str]:
        permissions = manifest.permissions
        requested = {"network"} if permissions.network else set()
        requested |= {"mqtt"} if permissions.mqtt else set()
        requested |= {"host_network"} if permissions.host_network else set()
        requested |= {"usb"} if permissions.usb else set()
        requested |= {"gpio"} if permissions.gpio else set()
        requested |= {f"serial:{item}" for item in permissions.serial_devices}
        return requested

    @staticmethod
    def _container_name(extension_id: str) -> str:
        if not re.fullmatch(r"[a-z0-9._-]+", extension_id):
            raise ExtensionRuntimeError("Invalid extension ID")
        return f"blackbone-ext-{extension_id.replace('.', '-') }"

    @staticmethod
    def _docker(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(["docker", *arguments], text=True, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExtensionRuntimeError("Docker is unavailable or did not respond") from exc
        if check and result.returncode:
            raise ExtensionRuntimeError(result.stderr.strip() or "Docker operation failed")
        return result

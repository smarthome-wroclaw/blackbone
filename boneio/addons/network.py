"""Network policy for fetching untrusted add-on repositories."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import aiohttp

from boneio.addons.errors import AddonError

INDEX_LIMIT = 2 * 1024 * 1024
MANIFEST_LIMIT = 256 * 1024
FILE_LIMIT = 2 * 1024 * 1024
MAX_REDIRECTS = 3


def _decoded_path(path: str) -> str:
    decoded = path
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise AddonError("invalid_url", "Repository file URL contains an invalid port.") from exc
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def canonical_repository_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise AddonError("unsafe_repository_url", "Repository URL must use HTTPS.")
    if parsed.username or parsed.password or parsed.fragment:
        raise AddonError(
            "unsafe_repository_url",
            "Repository URL cannot contain credentials or a fragment.",
        )
    decoded_path = _decoded_path(parsed.path)
    if any(segment in {".", ".."} for segment in decoded_path.split("/")) or "\\" in decoded_path:
        raise AddonError("unsafe_repository_url", "Repository URL contains an unsafe path.")
    host = parsed.hostname.lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError as exc:
        raise AddonError("unsafe_repository_url", "Repository URL contains an invalid port.") from exc
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port in {None, 443} else f"{rendered_host}:{port}"
    path = parsed.path or "/"
    return urlunsplit(("https", netloc, path, parsed.query, ""))


def resolve_same_origin(index_url: str, candidate: str) -> str:
    if not isinstance(candidate, str) or not candidate:
        raise AddonError("invalid_url", "Repository entry contains an invalid file URL.")
    resolved = urljoin(index_url, candidate)
    parsed = urlsplit(resolved)
    if parsed.username or parsed.password or parsed.fragment or parsed.scheme != "https":
        raise AddonError("cross_origin_url", "Repository files must use the repository HTTPS origin.")
    if origin(resolved) != origin(index_url):
        raise AddonError("cross_origin_url", "Repository files must stay on the repository origin.")
    decoded_path = _decoded_path(parsed.path)
    if any(segment in {".", ".."} for segment in decoded_path.split("/")) or "\\" in decoded_path:
        raise AddonError("unsafe_file_url", "Repository file URL contains an unsafe path.")
    return resolved


def is_public_address(address: str) -> bool:
    try:
        value = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return not (
        value.is_private
        or value.is_loopback
        or value.is_link_local
        or value.is_multicast
        or value.is_reserved
        or value.is_unspecified
    )


class PublicResolver(aiohttp.abc.AbstractResolver):
    """Resolve and pin only globally routable destination addresses."""

    async def resolve(self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET):
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, port, family=family, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise AddonError(
                "repository_unavailable", "Repository host could not be resolved.", status_code=502
            ) from exc
        results: list[dict[str, object]] = []
        seen: set[str] = set()
        for actual_family, _, protocol, _, sockaddr in infos:
            address = sockaddr[0]
            if address in seen:
                continue
            seen.add(address)
            if not is_public_address(address):
                raise AddonError("unsafe_destination", "Repository resolves to a blocked network address.")
            results.append(
                {
                    "hostname": host,
                    "host": address,
                    "port": port,
                    "family": actual_family,
                    "proto": protocol,
                    "flags": socket.AI_NUMERICHOST,
                }
            )
        if not results:
            raise AddonError("repository_unavailable", "Repository host has no usable address.", status_code=502)
        return results

    async def close(self) -> None:
        return None


@dataclass(frozen=True)
class FetchResult:
    body: bytes | None
    etag: str | None
    not_modified: bool = False


class SafeFetcher:
    def __init__(
        self,
        *,
        connect_timeout: float = 5,
        read_timeout: float = 10,
        total_timeout: float = 20,
    ) -> None:
        self.timeout = aiohttp.ClientTimeout(total=total_timeout, connect=connect_timeout, sock_read=read_timeout)

    async def fetch(self, url: str, *, limit: int, etag: str | None = None) -> FetchResult:
        initial_url = canonical_repository_url(url)
        connector = aiohttp.TCPConnector(resolver=PublicResolver(), ttl_dns_cache=0)
        headers = {"Accept": "application/json, application/yaml, text/yaml", "User-Agent": "BlackBone-Addons/1"}
        if etag:
            headers["If-None-Match"] = etag
        current_url = initial_url
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=self.timeout) as session:
                for _ in range(MAX_REDIRECTS + 1):
                    async with session.get(current_url, headers=headers, allow_redirects=False) as response:
                        if response.status == 304:
                            return FetchResult(None, etag, True)
                        if response.status in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location:
                                raise AddonError(
                                    "repository_unavailable",
                                    "Repository returned an invalid redirect.",
                                    status_code=502,
                                )
                            redirected = resolve_same_origin(initial_url, location)
                            current_url = redirected
                            continue
                        if response.status != 200:
                            raise AddonError("repository_unavailable", "Repository request failed.", status_code=502)
                        declared_length = response.content_length
                        if declared_length is not None and declared_length > limit:
                            raise AddonError("download_too_large", "Repository response exceeds the size limit.")
                        body = await response.content.read(limit + 1)
                        if len(body) > limit:
                            raise AddonError("download_too_large", "Repository response exceeds the size limit.")
                        return FetchResult(body, response.headers.get("ETag"))
                raise AddonError("unsafe_redirect", "Repository redirected too many times.", status_code=502)
        except AddonError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise AddonError("repository_unavailable", "Repository could not be reached.", status_code=502) from exc

"""Forward configured MQTT topic payloads to virtual Loxone UDP inputs."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from boneio.core.messaging.basic import MessageBus
from boneio.core.messaging.lox import LoxUDPClient

_LOGGER = logging.getLogger(__name__)


class LoxMqttBridge:
    """Bridge arbitrary MQTT topic payloads to named Loxone UDP inputs."""

    def __init__(
        self,
        message_bus: MessageBus,
        lox_bus: LoxUDPClient,
        mappings: list[dict],
    ) -> None:
        self._message_bus = message_bus
        self._lox_bus = lox_bus
        self._mappings = mappings

    @staticmethod
    def _make_callback(
        lox_bus: LoxUDPClient,
        device_id: str,
    ) -> Callable[[str, str], Awaitable[None]]:
        async def forward_payload(topic: str, payload: str) -> None:
            _LOGGER.debug(
                "Forwarding MQTT topic %s to Lox UDP input %s",
                topic,
                device_id,
            )
            lox_bus.send_udp(device_id, payload)

        return forward_payload

    async def start(self) -> None:
        """Subscribe to every configured MQTT topic."""
        for mapping in self._mappings:
            topic = mapping["topic"]
            device_id = mapping["device_id"]
            callback = self._make_callback(self._lox_bus, device_id)
            await self._message_bus.subscribe_and_listen(topic, callback)
            _LOGGER.info(
                "Lox MQTT bridge subscribed to %s for UDP input %s",
                topic,
                device_id,
            )

    async def stop(self) -> None:
        """Unsubscribe from every configured MQTT topic."""
        for mapping in self._mappings:
            await self._message_bus.unsubscribe_and_stop_listen(mapping["topic"])

"""Tests for the motionEye integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from motioneye_client.client import (
    MotionEyeClient,
    MotionEyeClientError,
    MotionEyeClientInvalidAuthError,
)
from motioneye_client.const import KEY_CAMERAS, KEY_ID, KEY_NAME

from homeassistant.components.camera.const import DOMAIN as CAMERA_DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_SOURCE, CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADMIN_PASSWORD,
    CONF_ADMIN_USERNAME,
    CONF_CLIENT,
    CONF_CONFIG_ENTRY,
    CONF_COORDINATOR,
    CONF_ON_UNLOAD,
    CONF_SURVEILLANCE_PASSWORD,
    CONF_SURVEILLANCE_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MOTIONEYE_MANUFACTURER,
    SIGNAL_CAMERA_ADD,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [CAMERA_DOMAIN]


def create_motioneye_client(
    *args: Any,
    **kwargs: Any,
) -> MotionEyeClient:
    """Create a MotionEyeClient."""
    return MotionEyeClient(*args, **kwargs)


def get_motioneye_device_unique_id(config_entry_id: str, camera_id: int) -> str:
    """Get the unique_id for a motionEye device."""
    return f"{config_entry_id}_{camera_id}"


def _split_motioneye_device_unique_id(
    device_unique_id: str,
) -> tuple[str, int] | None:
    """Split a unique_id into a (config_entry_id, camera index) tuple."""
    data = device_unique_id.split("_", 1)
    try:
        return (data[0], int(data[1])) if data else None
    except (ValueError, IndexError):
        pass
    return None


def get_motioneye_entity_unique_id(
    config_entry_id: str, camera_id: int, entity_type: str
) -> str:
    """Get the unique_id for a motionEye entity."""
    return f"{config_entry_id}_{camera_id}_{entity_type}"


def get_camera_from_cameras(
    camera_id: int, data: dict[str, Any]
) -> dict[str, Any] | None:
    """Get an individual camera dict from a multiple cameras data response."""
    for camera in data.get(KEY_CAMERAS) or []:
        if camera.get(KEY_ID) == camera_id:
            val: dict[str, Any] = camera
            return val
    return None


def is_acceptable_camera(camera: dict[str, Any] | None) -> bool:
    """Determine if a camera dict is acceptable."""
    return bool(camera and KEY_ID in camera and KEY_NAME in camera)


@callback
def listen_for_new_cameras(
    hass: HomeAssistant,
    entry: ConfigEntry,
    add_func: Callable,
) -> None:
    """Listen for new cameras."""

    hass.data[DOMAIN][entry.entry_id][CONF_ON_UNLOAD].extend(
        [
            async_dispatcher_connect(
                hass,
                SIGNAL_CAMERA_ADD.format(entry.entry_id),
                add_func,
            ),
        ]
    )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the motionEye component."""
    hass.data[DOMAIN] = {}
    return True


async def _create_reauth_flow(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                CONF_SOURCE: SOURCE_REAUTH,
                CONF_CONFIG_ENTRY: config_entry,
            },
            data=config_entry.data,
        )
    )


async def _add_camera(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    client: MotionEyeClient,
    entry: ConfigEntry,
    camera_id: int,
    camera: dict[str, Any],
    device_id: str,
) -> None:
    """Add a motionEye camera to hass."""

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        manufacturer=MOTIONEYE_MANUFACTURER,
        model=MOTIONEYE_MANUFACTURER,
        name=camera[KEY_NAME],
    )

    async_dispatcher_send(
        hass,
        SIGNAL_CAMERA_ADD.format(entry.entry_id),
        camera,
    )


async def _async_entry_updated(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle entry updates."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up motionEye from a config entry."""
    client = create_motioneye_client(
        entry.data[CONF_URL],
        admin_username=entry.data.get(CONF_ADMIN_USERNAME),
        admin_password=entry.data.get(CONF_ADMIN_PASSWORD),
        surveillance_username=entry.data.get(CONF_SURVEILLANCE_USERNAME),
        surveillance_password=entry.data.get(CONF_SURVEILLANCE_PASSWORD),
    )

    try:
        await client.async_client_login()
    except MotionEyeClientInvalidAuthError:
        await client.async_client_close()
        await _create_reauth_flow(hass, entry)
        return False
    except MotionEyeClientError as exc:
        await client.async_client_close()
        raise ConfigEntryNotReady from exc

    async def async_update_data() -> dict[str, Any] | None:
        try:
            return await client.async_get_cameras()
        except MotionEyeClientError as exc:
            raise UpdateFailed("Error communicating with API") from exc

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=DEFAULT_SCAN_INTERVAL,
    )
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_CLIENT: client,
        CONF_COORDINATOR: coordinator,
        CONF_ON_UNLOAD: [],
    }

    current_cameras: set[str] = set()
    device_registry = await dr.async_get_registry(hass)

    def _async_process_motioneye_cameras() -> None:
        """Process motionEye camera additions and removals."""
        inbound_camera: set[str] = set()
        if KEY_CAMERAS not in coordinator.data:
            return

        for camera in coordinator.data[KEY_CAMERAS]:
            if not is_acceptable_camera(camera):
                return
            camera_id = camera[KEY_ID]
            device_unique_id = get_motioneye_device_unique_id(entry.entry_id, camera_id)
            inbound_camera.add(device_unique_id)

            if device_unique_id in current_cameras:
                continue
            current_cameras.add(device_unique_id)
            hass.async_create_task(
                _add_camera(
                    hass,
                    device_registry,
                    client,
                    entry,
                    camera_id,
                    camera,
                    device_unique_id,
                )
            )

        # Ensure every device associated with this config entry is still in the list of
        # motionEye cameras, otherwise remove the device (and thus entities).
        for device_entry in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        ):
            for (kind, key) in device_entry.identifiers:
                if kind == DOMAIN and key in inbound_camera:
                    break
            else:
                device_registry.async_remove_device(device_entry.id)

    async def setup_then_listen() -> None:
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_setup(entry, platform)
                for platform in PLATFORMS
            ]
        )
        hass.data[DOMAIN][entry.entry_id][CONF_ON_UNLOAD].append(
            coordinator.async_add_listener(_async_process_motioneye_cameras)
        )
        await coordinator.async_refresh()
        hass.data[DOMAIN][entry.entry_id][CONF_ON_UNLOAD].append(
            entry.add_update_listener(_async_entry_updated)
        )

    hass.async_create_task(setup_then_listen())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unload_ok:
        config_data = hass.data[DOMAIN].pop(entry.entry_id)
        await config_data[CONF_CLIENT].async_client_close()
        for func in config_data[CONF_ON_UNLOAD]:
            func()

    return unload_ok

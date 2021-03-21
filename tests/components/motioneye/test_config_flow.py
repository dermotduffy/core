"""Test the motionEye config flow."""
import logging
from unittest.mock import AsyncMock, patch

from motioneye_client.client import (
    MotionEyeClientConnectionFailure,
    MotionEyeClientInvalidAuth,
    MotionEyeClientRequestFailed,
)

from homeassistant import config_entries, data_entry_flow, setup
from homeassistant.components.motioneye.const import (
    CONF_PASSWORD_ADMIN,
    CONF_PASSWORD_SURVEILLANCE,
    CONF_USERNAME_ADMIN,
    CONF_USERNAME_SURVEILLANCE,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.typing import HomeAssistantType

from . import (
    TEST_HOST,
    TEST_PORT,
    create_mock_motioneye_client,
    create_mock_motioneye_config_entry,
)

_LOGGER = logging.getLogger(__name__)


async def test_user_success(hass: HomeAssistantType) -> None:
    """Test successful user flow."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] is None

    mock_client = create_mock_motioneye_client()

    with patch(
        "homeassistant.components.motioneye.config_flow.MotionEyeClient",
        return_value=mock_client,
    ), patch(
        "homeassistant.components.motioneye.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.motioneye.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: TEST_HOST,
                CONF_PORT: TEST_PORT,
                CONF_USERNAME_ADMIN: "admin-username",
                CONF_PASSWORD_ADMIN: "admin-password",
                CONF_USERNAME_SURVEILLANCE: "surveillance-username",
                CONF_PASSWORD_SURVEILLANCE: "surveillance-password",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["title"] == f"{TEST_HOST}:{TEST_PORT}"
    assert result["data"] == {
        CONF_HOST: TEST_HOST,
        CONF_PORT: TEST_PORT,
        CONF_USERNAME_ADMIN: "admin-username",
        CONF_USERNAME_SURVEILLANCE: "surveillance-username",
        CONF_PASSWORD_ADMIN: "admin-password",
        CONF_PASSWORD_SURVEILLANCE: "surveillance-password",
    }
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_invalid_auth(hass: HomeAssistantType) -> None:
    """Test invalid auth is handled correctly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_client = create_mock_motioneye_client()
    mock_client.async_client_login = AsyncMock(side_effect=MotionEyeClientInvalidAuth)

    with patch(
        "homeassistant.components.motioneye.config_flow.MotionEyeClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: TEST_HOST,
                CONF_PORT: TEST_PORT,
                CONF_USERNAME_ADMIN: "admin-username",
                CONF_PASSWORD_ADMIN: "admin-password",
                CONF_USERNAME_SURVEILLANCE: "surveillance-username",
                CONF_PASSWORD_SURVEILLANCE: "surveillance-password",
            },
        )
        await mock_client.async_client_close()

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_cannot_connect(hass: HomeAssistantType) -> None:
    """Test connection failure is handled correctly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_client = create_mock_motioneye_client()
    mock_client.async_client_login = AsyncMock(
        side_effect=MotionEyeClientConnectionFailure
    )

    with patch(
        "homeassistant.components.motioneye.config_flow.MotionEyeClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: TEST_HOST,
                CONF_PORT: TEST_PORT,
                CONF_USERNAME_ADMIN: "admin-username",
                CONF_PASSWORD_ADMIN: "admin-password",
                CONF_USERNAME_SURVEILLANCE: "surveillance-username",
                CONF_PASSWORD_SURVEILLANCE: "surveillance-password",
            },
        )
        await mock_client.async_client_close()

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_request_error(hass: HomeAssistantType) -> None:
    """Test a request error is handled correctly."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_client = create_mock_motioneye_client()
    mock_client.async_client_login = AsyncMock(side_effect=MotionEyeClientRequestFailed)

    with patch(
        "homeassistant.components.motioneye.config_flow.MotionEyeClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: TEST_HOST,
                CONF_PORT: TEST_PORT,
                CONF_USERNAME_ADMIN: "admin-username",
                CONF_PASSWORD_ADMIN: "admin-password",
                CONF_USERNAME_SURVEILLANCE: "surveillance-username",
                CONF_PASSWORD_SURVEILLANCE: "surveillance-password",
            },
        )
        await mock_client.async_client_close()

    assert result["type"] == "form"
    assert result["errors"] == {"base": "unknown"}


async def test_reauth(hass: HomeAssistantType) -> None:
    """Test a reauth."""
    config_data = {
        CONF_HOST: TEST_HOST,
        CONF_PORT: TEST_PORT,
    }

    config_entry = create_mock_motioneye_config_entry(hass, data=config_data)

    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_REAUTH}
    )
    assert result["type"] == "form"
    assert result["errors"] is None

    mock_client = create_mock_motioneye_client()

    new_data = {
        CONF_HOST: TEST_HOST,
        CONF_PORT: TEST_PORT,
        CONF_USERNAME_ADMIN: "admin-username",
        CONF_PASSWORD_ADMIN: "admin-password",
        CONF_USERNAME_SURVEILLANCE: "surveillance-username",
        CONF_PASSWORD_SURVEILLANCE: "surveillance-password",
    }

    with patch(
        "homeassistant.components.motioneye.config_flow.MotionEyeClient",
        return_value=mock_client,
    ), patch(
        "homeassistant.components.motioneye.async_setup", return_value=True
    ) as mock_setup, patch(
        "homeassistant.components.motioneye.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            new_data,
        )
        await hass.async_block_till_done()

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "reauth_successful"
        assert config_entry.data == new_data

    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1
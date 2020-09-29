"""Tests for the Hyperion config flow."""

import logging

from asynctest import CoroutineMock
from hyperion import const

from homeassistant import data_entry_flow, setup
from homeassistant.components.hyperion.const import (
    CONF_AUTH_ID,
    CONF_CREATE_TOKEN,
    CONF_HYPERION_URL,
    CONF_INSTANCE,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN

from . import (
    TEST_HOST,
    TEST_HYPERION_URL,
    TEST_ID,
    TEST_INSTANCE,
    TEST_PORT,
    TEST_TOKEN,
    create_mock_client,
)

from tests.async_mock import patch
from tests.common import MockConfigEntry

_LOGGER = logging.getLogger(__name__)

TEST_USER_INPUT = {
    CONF_HOST: TEST_HOST,
    CONF_PORT: TEST_PORT,
    CONF_INSTANCE: TEST_INSTANCE,
}

TEST_AUTH_REQUIRED_RESP = {
    "command": "authorize-tokenRequired",
    "info": {
        "required": True,
    },
    "success": True,
    "tan": 1,
}

TEST_AUTH_ID = "ABCDE"
TEST_REQUEST_TOKEN_SUCCESS = {
    "command": "authorize-requestToken",
    "success": True,
    "info": {"comment": const.DEFAULT_ORIGIN, "id": TEST_AUTH_ID, "token": TEST_TOKEN},
}

TEST_REQUEST_TOKEN_FAIL = {
    "command": "authorize-requestToken",
    "success": False,
    "error": "Token request timeout or denied",
}


async def _create_mock_entry(hass):
    """Add a test Hyperion entity to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_ID,
        title=TEST_ID,
        data={
            "host": TEST_HOST,
            "port": TEST_PORT,
            "instance": TEST_INSTANCE,
        },
    )
    entry.add_to_hass(hass)

    # Setup
    client = create_mock_client()
    with patch("hyperion.client.HyperionClient", return_value=client):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def _init_flow(hass, source=SOURCE_USER):
    """Initialize a flow."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": source})


async def _configure_flow(hass, init_result, user_input={}):
    """Provide input to a flow."""
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], user_input=user_input
    )
    await hass.async_block_till_done()
    return result


async def test_user_if_no_configuration(hass):
    """Check flow aborts when no configuration is present."""
    result = await _init_flow(hass)

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"
    assert result["handler"] == DOMAIN


async def test_user_existing_id_abort(hass):
    """Verify a duplicate ID results in an abort."""
    result = await _init_flow(hass)

    await _create_mock_entry(hass)

    client = create_mock_client()
    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT


async def test_user_client_errors(hass):
    """Verify correct behaviour with client errors."""
    result = await _init_flow(hass)

    client = create_mock_client()

    # Two connection attempts are made: fail the first one.
    client.async_client_connect = CoroutineMock(side_effect=lambda raw: not raw)
    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "connection_error"

    # Two connection attempts are made: fail the second one.
    client.async_client_connect = CoroutineMock(side_effect=lambda raw: raw)
    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "connection_error"

    # Fail the auth check call.
    client.async_client_connect = CoroutineMock(return_value=True)
    client.async_is_auth_required = CoroutineMock(return_value={"success": False})
    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["errors"]["base"] == "auth_required_error"


async def test_user_noauth_flow_success(hass):
    """Check a full flow without auth."""
    result = await _init_flow(hass)

    client = create_mock_client()
    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["handler"] == DOMAIN
    assert result["title"] == client.id
    assert result["data"] == TEST_USER_INPUT


async def test_user_auth_required(hass):
    """Verify correct behaviour when auth is required."""
    result = await _init_flow(hass)

    client = create_mock_client()
    client.async_is_auth_required = CoroutineMock(return_value=TEST_AUTH_REQUIRED_RESP)

    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "auth"


async def test_auth_static_token(hass):
    """Verify correct behaviour with a static token."""
    result = await _init_flow(hass)

    client = create_mock_client()
    client.async_is_auth_required = CoroutineMock(return_value=TEST_AUTH_REQUIRED_RESP)

    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "auth"

    def get_client_check_token(*args, **kwargs):
        assert kwargs[CONF_TOKEN] == TEST_TOKEN
        return client

    # First, fail the auth connection (should return be to the auth window)
    client.async_client_connect = CoroutineMock(return_value=False)
    with patch("hyperion.client.HyperionClient", side_effect=get_client_check_token):
        result = await _configure_flow(
            hass, result, user_input={CONF_CREATE_TOKEN: False, CONF_TOKEN: TEST_TOKEN}
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "auth"
        assert result["errors"]["base"] == "auth_error"

    # Now succeed, should create an entry.
    client.async_client_connect = CoroutineMock(return_value=True)
    with patch("hyperion.client.HyperionClient", side_effect=get_client_check_token):
        result = await _configure_flow(
            hass, result, user_input={CONF_CREATE_TOKEN: False, CONF_TOKEN: TEST_TOKEN}
        )
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["handler"] == DOMAIN
    assert result["title"] == client.id
    assert result["data"] == {**TEST_USER_INPUT, **{CONF_TOKEN: TEST_TOKEN}}


async def test_auth_create_token_approval_declined(hass):
    """Verify correct behaviour when a token request is declined."""
    result = await _init_flow(hass)

    client = create_mock_client()
    client.async_is_auth_required = CoroutineMock(return_value=TEST_AUTH_REQUIRED_RESP)

    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "auth"

    client.async_request_token = CoroutineMock(return_value=TEST_REQUEST_TOKEN_FAIL)
    with patch("hyperion.client.HyperionClient", return_value=client), patch(
        "hyperion.client.generate_random_auth_id", return_value=TEST_AUTH_ID
    ):
        result = await _configure_flow(
            hass, result, user_input={CONF_CREATE_TOKEN: True}
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "create_token"
        assert result["description_placeholders"] == {
            CONF_AUTH_ID: TEST_AUTH_ID,
            CONF_HYPERION_URL: TEST_HYPERION_URL,
        }

        result = await _configure_flow(hass, result)
        await hass.async_block_till_done()
        assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP
        assert result["step_id"] == "create_token_external"

        result = await _configure_flow(hass, result)
        assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP_DONE
        assert result["step_id"] == "create_token_fail"

        result = await _configure_flow(hass, result)
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "auth"
        assert result["errors"]["base"] == "auth_new_token_not_granted_error"


async def test_auth_create_token_when_issued_token_fails(hass):
    """Verify correct behaviour when a token is granted by fails to authenticate."""
    result = await _init_flow(hass)

    client = create_mock_client()
    client.async_is_auth_required = CoroutineMock(return_value=TEST_AUTH_REQUIRED_RESP)

    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "auth"

    client.async_request_token = CoroutineMock(return_value=TEST_REQUEST_TOKEN_SUCCESS)
    with patch("hyperion.client.HyperionClient", return_value=client), patch(
        "hyperion.client.generate_random_auth_id", return_value=TEST_AUTH_ID
    ):
        result = await _configure_flow(
            hass, result, user_input={CONF_CREATE_TOKEN: True}
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "create_token"
        assert result["description_placeholders"] == {
            CONF_AUTH_ID: TEST_AUTH_ID,
            CONF_HYPERION_URL: TEST_HYPERION_URL,
        }

        result = await _configure_flow(hass, result)
        assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP
        assert result["step_id"] == "create_token_external"

        result = await _configure_flow(hass, result)
        await hass.async_block_till_done()
        assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP_DONE
        assert result["step_id"] == "create_token_success"

        # Make the last verification fail.
        client.async_client_connect = CoroutineMock(return_value=False)

        result = await _configure_flow(hass, result)
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "auth"
        assert result["errors"]["base"] == "auth_new_token_not_work_error"


async def test_auth_create_token_success(hass):
    """Verify correct behaviour when a token is successfully created."""
    result = await _init_flow(hass)

    client = create_mock_client()
    client.async_is_auth_required = CoroutineMock(return_value=TEST_AUTH_REQUIRED_RESP)

    with patch("hyperion.client.HyperionClient", return_value=client):
        result = await _configure_flow(hass, result, user_input=TEST_USER_INPUT)
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "auth"

    client.async_request_token = CoroutineMock(return_value=TEST_REQUEST_TOKEN_SUCCESS)
    with patch("hyperion.client.HyperionClient", return_value=client), patch(
        "hyperion.client.generate_random_auth_id", return_value=TEST_AUTH_ID
    ):
        result = await _configure_flow(
            hass, result, user_input={CONF_CREATE_TOKEN: True}
        )
        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "create_token"
        assert result["description_placeholders"] == {
            CONF_AUTH_ID: TEST_AUTH_ID,
            CONF_HYPERION_URL: TEST_HYPERION_URL,
        }

        result = await _configure_flow(hass, result)
        assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP
        assert result["step_id"] == "create_token_external"

        result = await _configure_flow(hass, result)
        await hass.async_block_till_done()
        assert result["type"] == data_entry_flow.RESULT_TYPE_EXTERNAL_STEP_DONE
        assert result["step_id"] == "create_token_success"

        result = await _configure_flow(hass, result)
        assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
        assert result["handler"] == DOMAIN
        assert result["title"] == client.id
        assert result["data"] == {**TEST_USER_INPUT, **{CONF_TOKEN: TEST_TOKEN}}

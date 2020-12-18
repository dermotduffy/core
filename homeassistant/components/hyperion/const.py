"""Constants for Hyperion integration."""
COLOR_BLACK = (0, 0, 0)

DOMAIN = "hyperion"

DEFAULT_NAME = "Hyperion"
DEFAULT_ORIGIN = "Home Assistant"
DEFAULT_PRIORITY = 128

CONF_AUTH_ID = "auth_id"
CONF_CREATE_TOKEN = "create_token"
CONF_INSTANCE = "instance"
CONF_MODE_OFF = "mode_off"
CONF_MODE_OFF_LED_DEVICE = "led_device"
CONF_MODE_OFF_SET_BLACK = "set_black"
CONF_PRIORITY = "priority"
DEFAULT_MODE_OFF = CONF_MODE_OFF_LED_DEVICE

CONF_ROOT_CLIENT = "ROOT_CLIENT"
CONF_ON_UNLOAD = "ON_UNLOAD"

SIGNAL_INSTANCES_UPDATED = f"{DOMAIN}_instances_updated_signal." "{}"
SIGNAL_INSTANCE_REMOVED = f"{DOMAIN}_instance_removed_signal." "{}"

SOURCE_IMPORT = "import"

HYPERION_VERSION_WARN_CUTOFF = "2.0.0-alpha.9"
HYPERION_RELEASES_URL = "https://github.com/hyperion-project/hyperion.ng/releases"

TYPE_HYPERION_LIGHT = "hyperion_light"

"""Constants for the IDFM integration."""

DOMAIN = "idfm"
NAME = "IDFM"

PLATFORMS = ["sensor"]

CONF_TOKEN = "api_token"
CONF_KIND = "kind"
CONF_MODE = "mode"
CONF_LINE = "line_id"
CONF_LINE_NAME = "line_name"
CONF_STOP = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_DIRECTION = "direction"
CONF_DESTINATION = "destination"

KIND_TRAFFIC = "traffic"
KIND_DEPARTURES = "departures"

SCAN_INTERVAL_TRAFFIC = 180
SCAN_INTERVAL_DEPARTURES = 60

STATE_NORMAL = "normal"
STATE_INFO = "info"
STATE_DISRUPTED = "perturbe"
STATE_BLOCKING = "bloque"

# Navitia disruption "effect" values that are considered service-blocking.
BLOCKING_EFFECTS = {"NO_SERVICE", "DETOUR", "STOP_MOVED", "REDUCED_SERVICE"}
# Effects considered a lighter disruption rather than just an informational note.
DISRUPTED_EFFECTS = {"SIGNIFICANT_DELAYS", "MODIFIED_SERVICE", "UNKNOWN_EFFECT"}

MODE_ICONS = {
    "metro": "mdi:subway-variant",
    "rail": "mdi:train",
    "tram": "mdi:tram",
    "bus": "mdi:bus",
}

ATTR_LINE_ID = "line_id"
ATTR_LINE_NAME = "line_name"
ATTR_MODE = "mode"
ATTR_SHORT_NAME = "short_name"
ATTR_COLOR = "color"
ATTR_TEXT_COLOR = "text_color"
ATTR_MESSAGE = "message"
ATTR_TITLE = "title"
ATTR_SEVERITY = "severity"
ATTR_EFFECT = "effect"
ATTR_DISRUPTION_COUNT = "disruption_count"

ATTR_STOP_NAME = "stop_name"
ATTR_DIRECTION = "direction"
ATTR_DESTINATION = "destination"
ATTR_DEPARTURES = "departures"

LINES_DATASET_URL = (
    "https://data.iledefrance-mobilites.fr/explore/dataset/referentiel-des-lignes/"
    "download/?format=json&timezone=Europe/Paris&lang=fr"
)

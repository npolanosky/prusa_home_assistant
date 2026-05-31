"""Constants for the Prusa Connect integration."""

DOMAIN = "prusa_connect"
MANUFACTURER = "Prusa Research"

CONF_API_KEY = "api_key"
CONF_HOST = "host"
CONF_PRINTER_UUID = "printer_uuid"
CONF_PRINTER_NAME = "printer_name"
CONF_PRINTER_TYPE = "printer_type"
CONF_CONNECTION_TYPE = "connection_type"

CONNECTION_TYPE_LOCAL = "local"
CONNECTION_TYPE_CLOUD = "cloud"

PRUSA_CONNECT_CLOUD_API = "https://connect-mobile-api.prusa3d.com/api/v1"

PLATFORMS = ["sensor", "camera"]

PRUSA_CONNECT_CARDS = [
    {
        "name": "Prusa Connect Cards",
        "filename": "prusa-connect-card.js",
        "version": "1.0.0",
    }
]

URL_BASE = "/prusa_connect"

PRINTER_STATES = [
    "IDLE",
    "BUSY",
    "PRINTING",
    "PAUSED",
    "FINISHED",
    "STOPPED",
    "ERROR",
    "ATTENTION",
    "READY",
    "OFFLINE",
    "UNKNOWN",
]

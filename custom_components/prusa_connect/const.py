"""Constants for the Prusa Connect integration."""

DOMAIN = "prusa_connect"
MANUFACTURER = "Prusa Research"

CONF_API_KEY = "api_key"
CONF_HOST = "host"
CONF_PRINTER_UUID = "printer_uuid"
CONF_PRINTER_NAME = "printer_name"
CONF_PRINTER_TYPE = "printer_type"
CONF_CONNECTION_TYPE = "connection_type"
CONF_AUTH_CODE = "auth_code"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"

CONNECTION_TYPE_LOCAL = "local"
CONNECTION_TYPE_CLOUD = "cloud"

# Cloud endpoints
PRUSA_CONNECT_CLOUD_API = "https://connect.prusa3d.com"
PRUSA_ACCOUNT_API = "https://account.prusa3d.com"

# OAuth2 (Authorization Code + PKCE) — mirrors the public PrusaSlicer client.
# See PrusaSlicer src/slic3r/Utils/ServiceConfig.cpp and
# src/slic3r/GUI/UserAccountCommunication.cpp / UserAccountSession.cpp.
PRUSA_OAUTH_CLIENT_ID = "oamhmhZez7opFosnwzElIgE2oGgI2iJORSkw587O"
PRUSA_OAUTH_REDIRECT_URI = "prusaslicer://login"
PRUSA_OAUTH_SCOPE = "basic_info"
PRUSA_OAUTH_AUTHORIZE_PATH = "/o/authorize/"
PRUSA_OAUTH_TOKEN_PATH = "/o/token/"

PLATFORMS = ["sensor", "camera", "button"]

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

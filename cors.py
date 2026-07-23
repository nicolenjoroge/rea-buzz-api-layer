import os
import logging
from flask_cors import CORS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed origins per environment
# ---------------------------------------------------------------------------
_ENV = os.environ.get("FLASK_ENV", "production").lower()

_PROD_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "")

if _PROD_ORIGINS:
    raw = [o.strip() for o in _PROD_ORIGINS.split(",") if o.strip()]
    _ORIGINS = "*" if raw == ["*"] else raw
elif _ENV == "development":
    # All local dev origins — Live Server, plain localhost, file://
    _ORIGINS = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "null",   # file:// origin
    ]
else:
    logger.warning("ALLOWED_ORIGINS not set and not in development — defaulting to wildcard.")
    _ORIGINS = "*"

logger.info("CORS origins: %s", _ORIGINS)

# ---------------------------------------------------------------------------
# CORS config
# ---------------------------------------------------------------------------
_CORS_CONFIG = {
    "origins":            _ORIGINS,
    "methods":            ["GET", "PUT", "POST", "DELETE", "OPTIONS"],  # OPTIONS required for preflight
    "allow_headers":      ["Content-Type", "Authorization"],            # Authorization needed for JWT
    "expose_headers":     ["Content-Type", "Content-Length"],
    "supports_credentials": False,
    "max_age":            600,                                          # preflight cache: 10 min
}

def init_cors(app):
    CORS(app, resources={r"/api/*": _CORS_CONFIG})
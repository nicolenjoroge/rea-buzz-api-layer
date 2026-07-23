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
    _ORIGINS = [o.strip() for o in _PROD_ORIGINS.split(",") if o.strip()]
elif _ENV == "development":
    _ORIGINS = ["http://localhost:5000", "http://127.0.0.1:5000"]  # adjust port as needed
else:
    # No origins configured in production — fail loudly
    raise RuntimeError("ALLOWED_ORIGINS must be set in staging/production")

logger.info("CORS origins: %s", _ORIGINS)

# ---------------------------------------------------------------------------
# CORS config
# ---------------------------------------------------------------------------
_CORS_CONFIG = {
    "origins":        _ORIGINS,
    "methods":        ["GET", "PUT", "POST", "DELETE"],       # only what your routes actually use
    "allow_headers":  ["Content-Type"],             # no Authorization needed
    "expose_headers": [],
    "supports_credentials": False,                  # no cookies/auth headers
    "max_age":        600,                          # preflight cache: 10 min
}

def init_cors(app):
    CORS(app, resources={r"/api/*": _CORS_CONFIG})
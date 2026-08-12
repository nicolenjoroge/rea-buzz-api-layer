"""
database.py
-----------
Thread-safe Cosmos DB client using Managed Identity (passwordless).

No connection strings or secrets needed — Azure handles auth automatically.

Local dev:  run `az login` once, DefaultAzureCredential picks it up
Production: enable System-assigned Managed Identity on the App Service,
            then grant it "Cosmos DB Built-in Data Contributor" role
            in the Cosmos DB account → Data Explorer → Settings

Environment variables (App Service → Configuration):
  COSMOS_ENDPOINT   — e.g. https://your-account.documents.azure.com:443/
  DATABASE_NAME     — Cosmos database name
  CONTAINER_NAME    — default container (can be overridden per-call)

No COSMOS_CONNECTION_STRING or keys needed.
"""

import logging
import os
import threading

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("dashboard")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENDPOINT       = os.getenv("COSMOS_ENDPOINT")
DB_NAME = os.environ.get("DATABASE_NAME") or os.environ.get("COSMOS_DB")
CONTAINER_NAME = os.getenv("CONTAINER_NAME") or os.environ.get("COSMOS_CONTAINER")

# ---------------------------------------------------------------------------
# Thread-safe singletons
# ---------------------------------------------------------------------------

_lock       = threading.Lock()
_client     = None
_database   = None
_containers = {}   # cache by container name


def get_client() -> CosmosClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:  # double-checked locking
                if not ENDPOINT:
                    raise RuntimeError(
                        "Missing COSMOS_ENDPOINT — set it in App Service Configuration"
                    )
                
                _client = CosmosClient(
                    url=ENDPOINT,
                    credential=DefaultAzureCredential(),
                )
                log.info("Cosmos client initialised (Managed Identity)")
    return _client


def get_database():
    global _database
    if _database is None:
        with _lock:
            if _database is None:
                if not DB_NAME:
                    raise RuntimeError(
                        "Missing DATABASE_NAME — set it in App Service Configuration"
                    )
                _database = get_client().get_database_client(DB_NAME)
                log.info("Connected to Cosmos database '%s'", DB_NAME)
    return _database


def get_container(container_name: str = None):
    """
    Return a cached container client.
    Defaults to CONTAINER_NAME env var if container_name is not specified.
    """
    name = container_name or CONTAINER_NAME
    if not name:
        raise RuntimeError(
            "Missing CONTAINER_NAME — set it in App Service Configuration "
            "or pass container_name explicitly"
        )

    if name not in _containers:
        with _lock:
            if name not in _containers:
                _containers[name] = get_database().get_container_client(name)
                log.info("Container client cached for '%s'", name)

    return _containers[name]


# ---------------------------------------------------------------------------
# Startup health check
# ---------------------------------------------------------------------------

def validate_connection() -> bool:
    """
    Call once on app startup to fail fast if Cosmos is unreachable.
    Uses a lightweight db.read() — no data scanned.
    """
    try:
        get_database().read()
        log.info("Cosmos DB connection validated — database '%s' reachable", DB_NAME)
        return True
    except exceptions.CosmosHttpResponseError as e:
        log.error("Cosmos DB HTTP error: %s %s", e.status_code, e.message)
        raise
    except Exception as e:
        log.error("Cosmos DB connection failed: %s", e)
        raise


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    validate_connection()
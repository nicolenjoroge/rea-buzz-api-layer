"""
database.py
-----------
Thread-safe Cosmos DB client using connection string.

Environment variables:
    COSMOS_CONNECTION_STRING  — from Azure Portal → Cosmos DB → Keys → Primary Connection String
    DATABASE_NAME             — your Cosmos database name
    CONTAINER_NAME            — default container (bpmcontent)
"""

import logging
import os
import threading

from azure.cosmos import CosmosClient, exceptions
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING")
DB_NAME           = os.environ.get("COSMOS_DB")
CONTAINER_NAME    = os.environ.get("CONTAINER_NAME") or os.environ.get("COSMOS_CONTAINER")  # legacy env var

# ---------------------------------------------------------------------------
# Thread-safe singletons
# ---------------------------------------------------------------------------

_lock       = threading.Lock()
_client     = None
_database   = None
_containers = {}


def get_client() -> CosmosClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                if not CONNECTION_STRING:
                    raise RuntimeError(
                        "Missing COSMOS_CONNECTION_STRING — set it in App Service Configuration"
                    )
                _client = CosmosClient.from_connection_string(CONNECTION_STRING)
                log.info("Cosmos client initialised")
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
    Defaults to CONTAINER_NAME env var (bpmcontent) if not specified.
    """
    name = container_name or CONTAINER_NAME
    if not name:
        raise RuntimeError(
            "Missing CONTAINER_NAME — set it in App Service Configuration"
        )

    if name not in _containers:
        with _lock:
            if name not in _containers:
                _containers[name] = get_database().get_container_client(name)
                log.info("Container client cached for '%s'", name)

    return _containers[name]


def validate_connection() -> bool:
    """
    Lightweight startup check — reads database properties.
    Call once on app boot to fail fast if Cosmos is misconfigured.
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
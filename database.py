"""Connect to AZURE COSMOS DB, no Managed Identity"""

import os
from dotenv import load_dotenv
from azure.cosmos import CosmosClient

load_dotenv()

CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
DB_NAME = os.getenv("COSMOS_DB")
CONTAINER_NAME = os.getenv("COSMOS_CONTAINER")

client = None
database = None
container = None


def get_client():
    global client
    if client is None:
        if not CONNECTION_STRING:
            raise RuntimeError("Missing COSMOS_CONNECTION_STRING")
        client = CosmosClient.from_connection_string(CONNECTION_STRING)
    return client


def get_database():
    global database
    if database is None:
        if not DB_NAME:
            raise RuntimeError("Missing DATABASE_NAME")
        database = get_client().get_database_client(DB_NAME)
    return database


def get_container(container_name=None):
    global container
    if container_name is None:
        container_name = CONTAINER_NAME
    if not container_name:
        raise RuntimeError("Missing CONTAINER_NAME")
    if container is None or getattr(container, "_container_name", None) != container_name:
        container = get_database().get_container_client(container_name)
        container._container_name = container_name
    return container


def test_connection():
    try:
        get_database()
        print(f"Connection successful: connected to database '{DB_NAME}'")
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
"""
blob.py
Handles all reads and writes to Azure Blob Storage.
Uses the requests library — no Azure SDK needed.

Environment variables (set in .env):
  AZURE_STORAGE_ACCOUNT   — storage account name
  AZURE_STORAGE_SAS_TOKEN — SAS token (covers both containers)
  CONTENT_CONTAINER       — container holding content (manifest, draft, published)
  MEDIA_CONTAINER         — container holding media (images, videos)

Note: the SAS token is used only server-side. It is never returned to a caller.
All media access is proxied through media.py.
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

ACCOUNT           = os.environ["AZURE_STORAGE_ACCOUNT"]
SAS               = os.environ["AZURE_STORAGE_SAS_TOKEN"]
CONTENT_CONTAINER = os.environ["CONTENT_CONTAINER"]
MEDIA_CONTAINER   = os.environ["MEDIA_CONTAINER"]

BASE = f"https://{ACCOUNT}.blob.core.windows.net"


# ---------------------------------------------------------------------------
# Content container  (manifest, draft, published)
# ---------------------------------------------------------------------------

def _content_url(blob_name: str) -> str:
    return f"{BASE}/{CONTENT_CONTAINER}/{blob_name}?{SAS}"


def read_json(blob_name: str):
    """
    Read a blob from the content container and parse as JSON.
    Returns None if the blob does not exist (404).
    Raises on any other error.
    """
    resp = requests.get(_content_url(blob_name), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def write_json(blob_name: str, data: dict) -> None:
    """
    Write a dict as JSON to a blob in the content container.
    Creates the blob if it doesn't exist, overwrites if it does.
    """
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    resp = requests.put(
        _content_url(blob_name),
        data=body,
        headers={
            "x-ms-blob-type": "BlockBlob",
            "Content-Type":   "application/json; charset=utf-8",
        },
        timeout=30,
    )
    resp.raise_for_status()


def delete_blob(blob_name: str) -> None:
    """Delete a blob from the content container."""
    resp = requests.delete(_content_url(blob_name), timeout=10)
    if resp.status_code not in (200, 202, 404):  # 404 = already gone, that's fine
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Removed: list_media() and media_base_url()
#
# These functions previously returned raw Azure XML and the SAS token to
# callers, which exposed storage credentials to the browser.
# All media operations are now handled in media.py via proxy routes that
# keep the SAS token server-side at all times.
# ---------------------------------------------------------------------------
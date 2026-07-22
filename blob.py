"""
blob.py
Handles all reads and writes to Azure Blob Storage.
Uses the requests library — no Azure SDK needed.

Environment variables (set in .env):
  AZURE_STORAGE_ACCOUNT  — storage account name
  AZURE_STORAGE_SAS_TOKEN — SAS token (same one covers both containers)
  CONTENT_CONTAINER       — Container with the content
  MEDIA_CONTAINER         — Container with the media
"""

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

def _content_url(blob_name):
    return f"{BASE}/{CONTENT_CONTAINER}/{blob_name}?{SAS}"



def list_media():
    """
    List all blobs in the media container.
    Returns the raw XML response text from Azure.
    """
    url = f"{BASE}/{MEDIA_CONTAINER}?restype=container&comp=list&{SAS}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.text


def media_base_url():
    """
    Returns the base URL and SAS token for the media container.
    The frontend uses these to build <img> and <video> src URLs.
    """
    return {
        "baseUrl": f"{BASE}/{MEDIA_CONTAINER}",
        "sas": SAS,
    }

def delete_blob(blob_name: str) -> None:
    """Delete a blob from the content container."""
    resp = requests.delete(_content_url(blob_name), timeout=10)
    if resp.status_code not in (200, 202, 404):  # 404 = already gone, that's fine
        resp.raise_for_status()

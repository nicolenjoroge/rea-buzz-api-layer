"""
media.py
Proxy routes for all media operations.
The SAS token lives only on the server — it is never sent to the browser.

Routes added to app.py:
  GET  /api/media/list            — list blobs, returns clean JSON (not raw Azure XML)
  GET  /api/media/file/<path:name> — stream a blob back to the browser
  POST /api/media/upload          — upload a file from the browser to Azure
"""

import logging
import xml.etree.ElementTree as ET

import requests
from flask import Response, jsonify, request, stream_with_context

from blob import SAS, MEDIA_CONTAINER, BASE
from helpers import _err

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed file types for upload
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", "svg",   # images
    "mp4", "webm", "mov", "avi",                    # videos
}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 500 MB


def _media_url(blob_name: str) -> str:
    """Build a full Azure URL for a blob in the media container (SAS stays server-side)."""
    return f"{BASE}/{MEDIA_CONTAINER}/{blob_name}?{SAS}"


def _allowed(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# GET /api/media/list
# Returns a clean JSON list — no XML, no SAS, no Azure internals.
# ---------------------------------------------------------------------------
def get_media_list():
    url = f"{BASE}/{MEDIA_CONTAINER}?restype=container&comp=list&{SAS}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error("get_media_list: %s", e)
        return _err("Failed to list media", 500)

    # Parse Azure XML and return only the fields the frontend needs
    try:
        root = ET.fromstring(resp.text)
        blobs = []
        for blob in root.iter("Blob"):
            name = blob.findtext("Name") or ""
            size = blob.findtext("Properties/Content-Length") or "0"
            last_modified = blob.findtext("Properties/Last-Modified") or ""
            content_type = blob.findtext("Properties/Content-Type") or ""
            blobs.append({
                "name":         name,
                "size":         int(size),
                "lastModified": last_modified,
                "contentType":  content_type,
                # Give the frontend a ready-to-use proxy URL — no SAS exposed
                "url":          f"/api/media/file/{name}",
            })
    except ET.ParseError as e:
        logger.error("get_media_list XML parse error: %s", e)
        return _err("Failed to parse media list", 500)

    return jsonify({"blobs": blobs, "count": len(blobs)}), 200


# ---------------------------------------------------------------------------
# GET /api/media/file/<name>
# Streams the blob from Azure to the browser. No SAS in the browser URL.
# ---------------------------------------------------------------------------
def get_media_file(name: str):
    # Basic path traversal guard — blob names shouldn't contain ..
    if ".." in name or name.startswith("/"):
        return _err("Invalid file path", 400)

    azure_url = _media_url(name)

    try:
        azure_resp = requests.get(azure_url, stream=True, timeout=30)
    except Exception as e:
        logger.error("get_media_file fetch error [%s]: %s", name, e)
        return _err("Failed to fetch media file", 502)

    if azure_resp.status_code == 404:
        return _err("Media file not found", 404)

    if not azure_resp.ok:
        logger.error("get_media_file Azure error [%s]: %s", name, azure_resp.status_code)
        return _err("Failed to fetch media file", 502)

    # Forward only safe, necessary headers
    content_type    = azure_resp.headers.get("Content-Type", "application/octet-stream")
    content_length  = azure_resp.headers.get("Content-Length")

    headers = {"Content-Type": content_type}
    if content_length:
        headers["Content-Length"] = content_length

    return Response(
        stream_with_context(azure_resp.iter_content(chunk_size=65536)),
        status=200,
        headers=headers,
        direct_passthrough=True,
    )


# ---------------------------------------------------------------------------
# POST /api/media/upload
# Accepts a multipart file upload from the browser and writes it to Azure.
# The browser never touches Azure directly.
# ---------------------------------------------------------------------------
def post_media_upload():
    if "file" not in request.files:
        return _err("No file provided", 400)

    file = request.files["file"]
    filename = file.filename or ""

    if not filename:
        return _err("Filename is missing", 400)

    if not _allowed(filename):
        return _err(
            f"File type not allowed. Permitted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            415,
        )

    # Read into memory with a size guard
    data = file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return _err(f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024*1024)} MB", 413)

    # Determine subfolder from content type
    content_type = file.content_type or "application/octet-stream"
    subfolder = "videos" if content_type.startswith("video/") else "Images"
    blob_name = f"{subfolder}/{filename}"

    azure_url = _media_url(blob_name)

    try:
        resp = requests.put(
            azure_url,
            data=data,
            headers={
                "x-ms-blob-type": "BlockBlob",
                "Content-Type":   content_type,
                "Content-Length": str(len(data)),
            },
            timeout=60,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error("post_media_upload write error [%s]: %s", blob_name, e)
        return _err("Failed to upload file", 500)

    logger.info("Uploaded media: %s (%d bytes)", blob_name, len(data))
    return jsonify({
        "message":  "Uploaded successfully",
        "name":     blob_name,
        "url":      f"/api/media/file/{blob_name}",
        "size":     len(data),
    }), 201


# media.py — add this function

def delete_media_file():
    """
    Delete a blob from the media container.
    Called by the frontend — name comes from the request body, never from the URL.
    """
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")

    if not name or ".." in name or name.startswith("/"):
        return _err("Invalid file name", 400)

    azure_url = _media_url(name)
    try:
        resp = requests.delete(azure_url, timeout=10)
        if resp.status_code not in (200, 202, 404):
            resp.raise_for_status()
    except Exception as e:
        logger.error("delete_media_file [%s]: %s", name, e)
        return _err("Failed to delete file", 500)

    logger.info("Deleted media: %s", name)
    return jsonify({"message": "Deleted", "name": name}), 200
"""
app.py
Flask API for the REA Buzz Content Editor.

Blob layout:
  content/
    manifest.json
    draft/page.json
    published/v1.json, v2.json ...
  media/
    Images/...
    videos/...

Routes:
  GET  /api/draft                  — return draft/page.json
  PUT  /api/draft                  — save draft/page.json
  GET  /api/versions               — return manifest.json
  POST /api/publish                — snapshot draft → published/v{n}.json, update manifest
  POST /api/rollback               — restore published/v{n}.json → draft, flip liveVersion
  POST /api/discard                — revert draft to current live version

  GET  /api/media/list             — list media blobs (clean JSON, no SAS exposed)
  GET  /api/media/file/<path:name> — stream a media file (proxied, no SAS in URL)
  POST /api/media/upload           — upload a file to Azure via the backend proxy
"""

import logging
import os

from flask import Flask

from contentdraft import (
    get_draft, put_draft, get_versions,
    post_publish, post_rollback, post_discard,
)
from media import get_media_list, get_media_file, post_media_upload, delete_media_file
from cors import init_cors

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Limit incoming request bodies (guards PUT /api/draft and upload routes)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB (media upload ceiling)

# ---------------------------------------------------------------------------
# Setup CORS
# ---------------------------------------------------------------------------
init_cors(app)

# ---------------------------------------------------------------------------
# Prevent debug mode in production
# ---------------------------------------------------------------------------
if os.environ.get("FLASK_ENV") != "development" and os.environ.get("FLASK_DEBUG"):
    raise RuntimeError("FLASK_DEBUG must not be set in production")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content routes
# ---------------------------------------------------------------------------

@app.get("/api/draft")
def api_get_draft():
    return get_draft()


@app.put("/api/draft")
def api_put_draft():
    return put_draft()


@app.get("/api/versions")
def api_get_versions():
    return get_versions()


@app.post("/api/publish")
def api_post_publish():
    return post_publish()


@app.post("/api/rollback")
def api_post_rollback():
    return post_rollback()


@app.post("/api/discard")
def api_post_discard():
    return post_discard()


# ---------------------------------------------------------------------------
# Media proxy routes  (SAS token never leaves the server)
# ---------------------------------------------------------------------------

@app.get("/api/media-list")
def api_get_media_list():
    return get_media_list()


@app.get("/api/media-file/<path:name>")
def api_get_media_file(name: str):
    return get_media_file(name)


@app.post("/api/media-upload")
def api_post_media_upload():
    return post_media_upload()

# app.py — add this route alongside the other media routes

@app.delete("/api/media-delete")
def api_delete_media_file():
    return delete_media_file()

# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    app.run(debug=debug, port=port)
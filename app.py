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
  GET  /api/draft       — return draft/page.json
  PUT  /api/draft       — save draft/page.json
  GET  /api/versions    — return manifest.json
  POST /api/publish     — snapshot draft → published/v{n}.json, update manifest
  POST /api/rollback    — restore published/v{n}.json → draft, flip liveVersion
  GET  /api/media-list  — list blobs in media container (returns XML)
  GET  /api/media-url   — return base URL + SAS for media files

"""

import logging
import os

from flask import Flask
from flask_cors import CORS

from contentdraft import get_draft, put_draft, get_versions, post_publish, post_rollback, get_media_list, get_media_url, post_discard 
from cors import init_cors

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Setup CORS
# ---------------------------------------------------------------------------
init_cors(app)

# ---------------------------------------------------------------------------
# Prevent Debug enabled on Production
# ---------------------------------------------------------------------------
if os.environ.get("FLASK_ENV") != "development" and os.environ.get("FLASK_DEBUG"):
    raise RuntimeError("FLASK_DEBUG must not be set in production")


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)






# ---------------------------------------------------------------------------
# GET /api/draft
# ---------------------------------------------------------------------------

@app.get("/api/draft")
def api_get_draft():
    return get_draft()


# ---------------------------------------------------------------------------
# PUT /api/draft
# ---------------------------------------------------------------------------

@app.put("/api/draft")
def api_put_draft():
    return put_draft()


# ---------------------------------------------------------------------------
# GET /api/versions
# ---------------------------------------------------------------------------

@app.get("/api/versions")
def api_get_versions():
    return get_versions()


# ---------------------------------------------------------------------------
# POST /api/publish
# ---------------------------------------------------------------------------

@app.post("/api/publish")
def api_post_publish():
    return post_publish()


# ---------------------------------------------------------------------------
# POST /api/rollback
# ---------------------------------------------------------------------------

@app.post("/api/rollback")
def api_post_rollback():
    return post_rollback()


# ---------------------------------------------------------------------------
# POST /api/discard
# ---------------------------------------------------------------------------
@app.post("/api/discard")
def api_post_discard():
    return post_discard()

# ---------------------------------------------------------------------------
# GET /api/media-list
# ---------------------------------------------------------------------------

@app.get("/api/media-list")
def api_get_medialist():
    return get_media_list()


# ---------------------------------------------------------------------------
# GET /api/media-url
# ---------------------------------------------------------------------------

@app.get("/api/media-url")
def api_get_mediaurl():
    return get_media_url()


# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    app.run(debug=debug, port=port)
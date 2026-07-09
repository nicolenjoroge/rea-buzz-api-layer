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

Run locally:
  python app.py

Production:
  gunicorn app:app --bind 0.0.0.0:8000
"""

import logging
import os
import re
import uuid
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from blob import list_media, media_base_url, read_json, write_json
from database import get_container
from normalize import normalize_item, get_field

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# CORS
# Local dev: allow Live Server on 5500 and plain localhost
# Production: set ALLOWED_ORIGIN env var to your Static Web App URL
#             e.g. ALLOWED_ORIGIN=https://rea-buzz.azurestaticapps.net
_PROD_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "")
_ORIGINS = (
    [o.strip() for o in _PROD_ORIGINS.split(",") if o.strip()]
    if _PROD_ORIGINS
    else [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5501",
        "null",
    ]
)

CORS(app, resources={r"/api/*": {
    "origins":       _ORIGINS,
    "methods":       ["GET", "PUT", "POST", "OPTIONS", "DELETE", "PATCH"],
    "allow_headers": ["Content-Type"],
}})

#----------------------------------------------------------------------------------------------------
#LOGGING SETUP
#----------------------------------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Blob paths
DRAFT    = "draft/page.json"
MANIFEST = "manifest.json"

# Cosmos partitions
PARTITIONS   = ["AI", "RPA", "POWERAPPS", "POWERAGENTS", "IBPS", "DOCUSIGN"]
NAME_FIELDS  = ["processName", "process_name", "Process Name",
                "Process Name/Use Cases", "name"]


def _find_by_id(container, item_id):
    """Cross-partition lookup by Cosmos id."""
    try:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": item_id}],
            enable_cross_partition_query=True,
        ))
        return items[0] if items else None
    except Exception:
        logger.exception("Cross-partition lookup failed for id=%s", item_id)
        return None


def _extract_partition(payload):
    """Return uppercase partition value from payload, or None."""
    for key in ("sectionId", "section_id", "deliveryStream", "vertical"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    return None


def _normalized(raw):
    """Normalize a raw Cosmos item and include id + sectionId for the frontend."""
    norm = normalize_item(raw)
    norm["id"] = raw.get("id")
    sec = (raw.get("sectionId") or raw.get("section_id") or
           raw.get("deliveryStream") or raw.get("vertical"))
    if isinstance(sec, str):
        norm["sectionId"] = sec.strip().lower()
    return norm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc).isoformat()


def _err(msg, status=400, **extra):
    return jsonify({"error": msg, **extra}), status


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200



# ---------------------------------------------------------------------------
# GET /api/draft
# ---------------------------------------------------------------------------




@app.get("/api/draft")
def get_draft():
    try:
        data = read_json(DRAFT)
    except Exception as e:
        logger.error("get_draft: %s", e)
        return _err("Failed to read draft", 500)

    if data is None:
        return _err("draft/page.json not found", 404)

    return jsonify(data), 200


# ---------------------------------------------------------------------------
# PUT /api/draft
# ---------------------------------------------------------------------------

@app.put("/api/draft")
def put_draft():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return _err("Body must be a JSON object")

    data["lastSavedAt"] = _now()

    try:
        write_json(DRAFT, data)
    except Exception as e:
        logger.error("put_draft: %s", e)
        return _err("Failed to save draft", 500)

    return jsonify({"message": "Draft saved", "lastSavedAt": data["lastSavedAt"]}), 200


# ---------------------------------------------------------------------------
# GET /api/versions
# ---------------------------------------------------------------------------

@app.get("/api/versions")
def get_versions():
    try:
        manifest = read_json(MANIFEST)
    except Exception as e:
        logger.error("get_versions: %s", e)
        return _err("Failed to read manifest", 500)

    if manifest is None:
        return _err("manifest.json not found — nothing published yet", 404)

    return jsonify(manifest), 200


# ---------------------------------------------------------------------------
# POST /api/publish
# ---------------------------------------------------------------------------

@app.post("/api/publish")
def post_publish():
    body         = request.get_json(silent=True) or {}
    published_by = body.get("publishedBy", "unknown")

    # Read draft
    try:
        draft = read_json(DRAFT)
    except Exception as e:
        logger.error("post_publish read draft: %s", e)
        return _err("Failed to read draft", 500)

    if draft is None:
        return _err("No draft found", 404)

    # Read or initialise manifest
    try:
        manifest = read_json(MANIFEST) or {
            "currentVersion": 0,
            "liveVersion":    0,
            "versions":       [],
        }
    except Exception as e:
        logger.error("post_publish read manifest: %s", e)
        return _err("Failed to read manifest", 500)

    # Increment version
    n            = manifest["currentVersion"] + 1
    published_at = _now()
    version_tag  = f"v{n}"

    # Write snapshot
    snapshot = {**draft, "version": version_tag,
                "publishedAt": published_at, "publishedBy": published_by}
    try:
        write_json(f"published/{version_tag}.json", snapshot)
    except Exception as e:
        logger.error("post_publish write snapshot: %s", e)
        return _err("Failed to write snapshot", 500)

    # Update manifest
    manifest["currentVersion"] = n
    manifest["liveVersion"]    = n
    manifest.setdefault("versions", []).insert(0, {
        "version":     version_tag,
        "publishedAt": published_at,
        "publishedBy": published_by,
    })
    try:
        write_json(MANIFEST, manifest)
    except Exception as e:
        logger.error("post_publish write manifest: %s", e)
        return _err("Failed to update manifest", 500)

    logger.info("Published %s by %s", version_tag, published_by)
    return jsonify({
        "message":     f"Published as {version_tag}",
        "version":     version_tag,
        "publishedAt": published_at,
    }), 200


# ---------------------------------------------------------------------------
# POST /api/rollback
# ---------------------------------------------------------------------------

@app.post("/api/rollback")
def post_rollback():
    body           = request.get_json(silent=True) or {}
    version        = body.get("version", "")
    rolled_back_by = body.get("rolledBackBy", "unknown")

    if not re.fullmatch(r"v\d+", version):
        return _err('version must be "v1", "v2", etc.')

    # Read target snapshot
    try:
        snapshot = read_json(f"published/{version}.json")
    except Exception as e:
        logger.error("post_rollback read snapshot: %s", e)
        return _err("Failed to read snapshot", 500)

    if snapshot is None:
        return _err(f"published/{version}.json not found", 404)

    # Strip snapshot metadata → restore as draft
    rolled_back_at = _now()
    draft = {
        k: v for k, v in snapshot.items()
        if k not in ("version", "publishedAt", "publishedBy")
    }
    draft["lastSavedAt"]  = rolled_back_at
    draft["restoredFrom"] = version

    try:
        write_json(DRAFT, draft)
    except Exception as e:
        logger.error("post_rollback write draft: %s", e)
        return _err("Failed to restore draft", 500)

    # Update manifest — flip liveVersion only
    try:
        manifest = read_json(MANIFEST)
    except Exception as e:
        logger.error("post_rollback read manifest: %s", e)
        return _err("Failed to read manifest", 500)

    if manifest is None:
        return _err("manifest.json not found", 500)

    manifest["liveVersion"] = int(version[1:])
    manifest["lastRollback"] = {
        "version":       version,
        "rolledBackAt":  rolled_back_at,
        "rolledBackBy":  rolled_back_by,
    }
    try:
        write_json(MANIFEST, manifest)
    except Exception as e:
        logger.error("post_rollback write manifest: %s", e)
        return _err("Failed to update manifest", 500)

    logger.info("Rolled back to %s by %s", version, rolled_back_by)
    return jsonify({
        "message":        f"Rolled back to {version}",
        "liveVersion":    version,
        "draftRestoredTo": version,
        "rolledBackAt":   rolled_back_at,
    }), 200


# ---------------------------------------------------------------------------
# GET /api/media-list
# Returns the raw Azure XML blob listing — main.js parses it as before
# ---------------------------------------------------------------------------

@app.get("/api/media-list")
def get_media_list():
    try:
        xml = list_media()
    except Exception as e:
        logger.error("get_media_list: %s", e)
        return _err("Failed to list media", 500)

    return Response(xml, mimetype="application/xml"), 200


# ---------------------------------------------------------------------------
# GET /api/media-url
# ---------------------------------------------------------------------------

@app.get("/api/media-url")
def get_media_url():
    return jsonify(media_base_url()), 200




# ---------------------------------------------------------------------------
# INITIATIVES — Cosmos DB CRUD
# ---------------------------------------------------------------------------

@app.get("/api/initiatives")
def list_initiatives():
    container = get_container()
    all_items = []
    for partition in PARTITIONS:
        try:
            all_items.extend(list(container.query_items(
                query="SELECT * FROM c",
                partition_key=partition,
            )))
        except Exception:
            logger.exception("Failed to query partition '%s'", partition)

    valid = [i for i in all_items if i and get_field(i, NAME_FIELDS)]
    logger.info("Returning %d initiative(s)", len(valid))
    return jsonify([_normalized(i) for i in valid]), 200


@app.get("/api/initiatives/<item_id>")
def get_initiative(item_id):
    raw = _find_by_id(get_container(), item_id)
    if not raw:
        return _err("Not found", 404)
    return jsonify(_normalized(raw)), 200


@app.post("/api/initiatives")
def create_initiative():
    payload = request.get_json(silent=True)
    if not payload:
        return _err("Missing JSON payload")

    partition = _extract_partition(payload)
    if not partition:
        return _err("Missing sectionId — must be one of: " + ", ".join(PARTITIONS))
    if partition not in PARTITIONS:
        return _err(f"Invalid sectionId '{partition}'")

    payload["sectionId"] = partition
    payload.setdefault("id", str(uuid.uuid4()))

    try:
        created = get_container().create_item(payload)
        return jsonify(_normalized(created)), 201
    except Exception:
        logger.exception("Create failed")
        return _err("Create failed", 500)


@app.put("/api/initiatives/<item_id>")
def update_initiative(item_id):
    payload = request.get_json(silent=True)
    if not payload:
        return _err("Missing JSON payload")

    container = get_container()
    existing  = _find_by_id(container, item_id)

    if existing:
        payload["id"] = existing["id"]
        # Partition key is immutable — always preserve the stored value
        for k in ("sectionId", "section_id", "deliveryStream", "vertical"):
            if existing.get(k):
                payload[k] = existing[k]
                break
    else:
        partition = _extract_partition(payload)
        if not partition or partition not in PARTITIONS:
            return _err("Missing or invalid sectionId for new item")
        payload["sectionId"] = partition
        payload.setdefault("id", item_id)

    try:
        updated = container.upsert_item(payload)
        return jsonify(_normalized(updated)), 200
    except Exception:
        logger.exception("Upsert failed for id=%s", item_id)
        return _err("Upsert failed", 500)


@app.delete("/api/initiatives/<item_id>")
def delete_initiative(item_id):
    container = get_container()
    existing  = _find_by_id(container, item_id)
    if not existing:
        return _err("Not found", 404)

    partition = (existing.get("sectionId") or existing.get("section_id") or
                 existing.get("deliveryStream") or existing.get("vertical"))
    if not partition:
        return _err("Cannot determine partition key", 500)

    try:
        container.delete_item(item=existing["id"], partition_key=partition)
        return jsonify({"ok": True}), 200
    except Exception:
        logger.exception("Delete failed for id=%s", item_id)
        return _err("Delete failed", 500)

AUDIT_BLOB = "audit/export-log.json"

@app.post("/api/audit/export")
def log_export():
    body = request.get_json(silent=True) or {}
    
    try:
        existing = read_json(AUDIT_BLOB) or []
        existing.insert(0, {
            "action":    "export",
            "stream":    body.get("stream", ""),
            "records":   body.get("records", 0),
            "exportedBy": body.get("exportedBy", "unknown"),
            "exportedAt": _now(),
        })
        # Keep last 500 entries
        write_json(AUDIT_BLOB, existing[:500])
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.error("audit log failed: %s", e)
        return jsonify({"ok": False}), 500

# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
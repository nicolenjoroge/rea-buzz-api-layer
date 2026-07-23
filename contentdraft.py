"""
All functions that handle, CRUD operations on the Content found on REA Buzz
"""
import logging
import re

from flask import Response, jsonify, request
from blob import list_media, media_base_url, read_json, write_json, delete_blob
from helpers import _now, _err


#Log Actions
logger = logging.getLogger(__name__)

#Draft and manifest name
DRAFT    = "draft/page.json"
MANIFEST = "manifest.json"


# ---------------------------------------------------------------------------
# GET Json draft file
# ---------------------------------------------------------------------------
def get_draft():
    try:
        data = read_json(DRAFT)
    except Exception as e:
        logger.error("get_draft: %s", e)
        return _err("Failed to read content draft", 500)

    if data is None:
        return _err("Content Draft not found", 404)

    return jsonify(data), 200


# ---------------------------------------------------------------------------
# Edit content on the content draft
# ---------------------------------------------------------------------------
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
# Read manifest file: Get the current version
# ---------------------------------------------------------------------------
def get_versions():
    try:
        manifest = read_json(MANIFEST)
    except Exception as e:
        logger.error("get_versions: %s", e)
        return _err("Failed to read manifest", 500)

    if manifest is None:
        return _err("manifest file not found — nothing published yet", 404)

    return jsonify(manifest), 200



# ---------------------------------------------------------------------------
# POST Content Draft for All
# ---------------------------------------------------------------------------
def post_publish():
    body         = request.get_json(silent=True) or {}
    published_by = body.get("publishedBy", "unknown")

    try:
        draft = read_json(DRAFT)
    except Exception as e:
        logger.error("post_publish read draft: %s", e)
        return _err("Failed to read draft", 500)

    if draft is None:
        return _err("No draft found", 404)

#Setup snapshot version on manifest file
    try:
        manifest = read_json(MANIFEST) or {
            "currentVersion": 0,
            "liveVersion":    0,
            "versions":       [],
        }
    except Exception as e:
        logger.error("post_publish read manifest: %s", e)
        return _err("Failed to read manifest", 500)

    manifest.setdefault("currentVersion", 0)
    manifest.setdefault("liveVersion",    0)
    manifest.setdefault("versions",       [])

    MAX_VERSIONS = 10

    # If we're at the limit, reset counter to 1 and delete the oldest blob
    if manifest["currentVersion"] >= MAX_VERSIONS:
        # Find the oldest version in the list
        if manifest["versions"]:
            oldest = manifest["versions"][-1]["version"]  # last item = oldest (newest-first list)
            try:
                delete_blob(f"published/{oldest}.json")
                logger.info("Deleted old snapshot: published/%s.json", oldest)
            except Exception as e:
                logger.warning("Could not delete old snapshot %s: %s", oldest, e)

        # Reset counter
        manifest["currentVersion"] = 0
        manifest["liveVersion"]    = 0
        manifest["versions"]       = []

    n = manifest["currentVersion"] + 1
    published_at = _now()
    version_tag  = f"v{n}"

    snapshot = {**draft, "version": version_tag,
                "publishedAt": published_at, "publishedBy": published_by}
    try:
        write_json(f"published/{version_tag}.json", snapshot)
    except Exception as e:
        logger.error("post_publish write snapshot: %s", e)
        return _err("Failed to write snapshot", 500)

    manifest["currentVersion"] = n
    manifest["liveVersion"]    = n
    manifest["versions"].insert(0, {
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
# Return to previous live version on 'Restore'
# ---------------------------------------------------------------------------
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


def post_discard():
    """
    Reverts draft/page.json to the current live published version.
    Unlike rollback, does NOT update manifest.liveVersion —
    the live site continues serving the same version unchanged.
    """
    body    = request.get_json(silent=True) or {}
    version = body.get("version", "")

    if not re.fullmatch(r"v\d+", version):
        return _err('version must be "v1", "v2", etc.')

    try:
        snapshot = read_json(f"published/{version}.json")
    except Exception as e:
        logger.error("post_discard: %s", e)
        return _err("Failed to read snapshot", 500)

    if snapshot is None:
        return _err(f"published/{version}.json not found", 404)

    # Strip snapshot metadata and restore as draft
    content = {k: v for k, v in snapshot.items()
               if k not in ("version", "publishedAt", "publishedBy")}
    content["lastSavedAt"] = _now()

    try:
        write_json(DRAFT, content)
    except Exception as e:
        logger.error("post_discard write draft: %s", e)
        return _err("Failed to restore draft", 500)

    return jsonify(content), 200
# ---------------------------------------------------------------------------
# Get ALL media from media container
# ---------------------------------------------------------------------------
def get_media_list():
    try:
        xml = list_media()
    except Exception as e:
        logger.error("get_media_list: %s", e)
        return _err("Failed to list media", 500)

    return Response(xml, mimetype="application/xml"), 200


# ---------------------------------------------------------------------------
# Get media URLs from media container
# ---------------------------------------------------------------------------
def get_media_url():
    return jsonify(media_base_url()), 200
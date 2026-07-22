"""
All helper functions ie. time, error formats
"""

from datetime import datetime, timezone
from flask import jsonify


#Get current time
def _now():
    return datetime.now(timezone.utc).isoformat()


#Set error message
def _err(msg, status=400, **extra):
    return jsonify({"error": msg, **extra}), status
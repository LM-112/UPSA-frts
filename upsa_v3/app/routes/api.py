import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from ..db import get_db
from ..services.engine import process_event

bp = Blueprint("api", __name__)


@bp.route("/health")
def health():
    return jsonify({"ok": True, "version": "1.0.0", "model": "DS-K1T323MBFWX-E1"})


@bp.route("/events/hik", methods=["POST"])
def hik_event():
    """Receive recognition events from the Hikvision DS-K1T323MBFWX-E1 terminal."""
    payload = {}
    if request.is_json:
        payload = request.get_json(silent=True) or {}
    else:
        raw = request.form.get("event_log") or request.data.decode("utf-8", errors="ignore")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}

    try:
        evt  = payload.get("AccessControllerEvent") or payload
        emp  = evt.get("employeeNoString") or evt.get("employeeNo")
        if not emp:
            return jsonify({"ok": False, "reason": "no employee id"}), 400
        sim  = evt.get("similarity")
        if sim and float(sim) > 1:
            sim = float(sim) / 100.0
        when = payload.get("dateTime") or evt.get("dateTime")
        try:
            occurred = datetime.fromisoformat(when.replace("Z", "+00:00")).replace(tzinfo=None) if when else datetime.utcnow()
        except Exception:
            occurred = datetime.utcnow()
        db = get_db()
        result = process_event(db, str(emp), float(sim) if sim else None, occurred)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/events/simulate", methods=["POST"])
def simulate_event():
    """Simulate a face recognition event for demo/defence purposes."""
    data = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id", "10300137")
    similarity  = float(data.get("similarity", 0.94))
    db = get_db()
    result = process_event(db, employee_id, similarity, datetime.utcnow())
    return jsonify(result)

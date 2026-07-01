"""Processes Hikvision recognition events into attendance records."""
from datetime import datetime, timedelta


def process_event(conn, employee_id, similarity, occurred_at):
    student = conn.execute(
        "SELECT * FROM students WHERE employee_id=?", (str(employee_id),)
    ).fetchone()
    if not student:
        return {"ok": False, "reason": "student_not_found"}
    if not student["consent_given"]:
        return {"ok": False, "reason": "no_consent"}

    # Minimum similarity threshold
    if similarity and similarity < 0.85:
        return {"ok": False, "reason": "low_similarity"}

    # Find matching open session
    session = _find_session(conn, student["id"], occurred_at)
    if not session:
        conn.execute(
            "INSERT INTO event_logs(employee_id_seen,similarity,occurred_at,processed) VALUES(?,?,?,0)",
            (str(employee_id), similarity, occurred_at.strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return {"ok": True, "reason": "no_matching_session"}

    # Classify status
    start_dt = datetime.strptime(
        f"{session['session_date']} {session['start_time']}", "%Y-%m-%d %H:%M"
    )
    grace_end = start_dt + timedelta(minutes=15)
    status = "present" if occurred_at <= grace_end else "late"
    mins_late = max(0, int((occurred_at - start_dt).total_seconds() / 60)) if status == "late" else 0

    # Upsert attendance record
    existing = conn.execute(
        "SELECT id FROM attendance_records WHERE session_id=? AND student_id=?",
        (session["id"], student["id"])
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE attendance_records SET status=?,check_in_time=?,minutes_late=?,similarity_score=?,source='terminal' WHERE id=?",
            (status, occurred_at.strftime("%Y-%m-%d %H:%M:%S"), mins_late, similarity, existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO attendance_records(session_id,student_id,status,check_in_time,minutes_late,similarity_score,source) VALUES(?,?,?,?,?,?,'terminal')",
            (session["id"], student["id"], status, occurred_at.strftime("%Y-%m-%d %H:%M:%S"), mins_late, similarity)
        )

    conn.execute(
        "INSERT INTO event_logs(employee_id_seen,similarity,occurred_at,matched_session,processed) VALUES(?,?,?,?,1)",
        (str(employee_id), similarity, occurred_at.strftime("%Y-%m-%d %H:%M:%S"), session["id"])
    )
    conn.commit()
    return {"ok": True, "status": status, "student": student["index_number"], "session": session["id"]}


def _find_session(conn, student_id, occurred_at):
    sd = occurred_at.strftime("%Y-%m-%d")
    # Find sessions that are open and match this student's registered courses + group
    sessions = conn.execute("""
        SELECT cs.* FROM class_sessions cs
        JOIN course_registrations cr ON cr.course_id = cs.course_id
        JOIN students s ON s.id = cr.student_id
        WHERE cs.session_date = ? AND cs.is_open = 1
          AND s.id = ?
          AND (cs.group_filter IS NULL OR cs.group_filter = s.group_name)
    """, (sd, student_id)).fetchall()
    for s in sessions:
        start = datetime.strptime(f"{sd} {s['start_time']}", "%Y-%m-%d %H:%M")
        end   = datetime.strptime(f"{sd} {s['end_time']}", "%Y-%m-%d %H:%M")
        if (start - timedelta(minutes=15)) <= occurred_at <= end:
            return s
    return None

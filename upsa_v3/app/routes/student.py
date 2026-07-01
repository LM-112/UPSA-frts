from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, abort
from ..db import q, q1, run

bp = Blueprint("student", __name__)


def stu_req(f):
    @wraps(f)
    def d(*a, **kw):
        if session.get("user", {}).get("role") != "student":
            abort(403)
        return f(*a, **kw)
    return d


def _me():
    uid = session["user"]["id"]
    return q1("""SELECT s.*,u.full_name,u.email,
                 p.name AS prog_name, p.code AS prog_code,
                 d.name AS dept_name, f.name AS faculty_name, f.code AS faculty_code
                 FROM students s JOIN users u ON u.id=s.user_id
                 LEFT JOIN programmes p ON p.id=s.programme_id
                 LEFT JOIN departments d ON d.id=p.department_id
                 LEFT JOIN faculties f ON f.id=d.faculty_id
                 WHERE s.user_id=?""", (uid,))


@bp.route("/")
@stu_req
def dashboard():
    me = _me()
    if not me:
        flash("Student profile not found. Contact administrator.", "warning")
        return render_template("student/dashboard.html", me=None, courses=[], summary={})

    regs = q("""SELECT c.id AS course_id, c.code, c.title, c.credit_hours,
                u2.full_name AS lecturer_name, l.title AS lec_title,
                COUNT(DISTINCT cs.id) AS total_sessions,
                COUNT(DISTINCT ar.id) FILTER(WHERE ar.status='present') AS present,
                COUNT(DISTINCT ar.id) FILTER(WHERE ar.status='late') AS late,
                COUNT(DISTINCT ar.id) FILTER(WHERE ar.status='absent') AS absent
                FROM course_registrations cr
                JOIN courses c ON c.id=cr.course_id
                LEFT JOIN lecturers l ON l.id=c.lecturer_id
                LEFT JOIN users u2 ON u2.id=l.user_id
                LEFT JOIN class_sessions cs ON cs.course_id=c.id
                  AND (cs.group_filter IS NULL OR cs.group_filter=?)
                LEFT JOIN attendance_records ar ON ar.session_id=cs.id AND ar.student_id=?
                WHERE cr.student_id=?
                GROUP BY c.id ORDER BY c.code""",
             (me["group_name"], me["id"], me["id"]))

    courses = []
    overall = {"present": 0, "late": 0, "absent": 0, "total": 0}
    for r in regs:
        total = r["total_sessions"] or 1
        att   = (r["present"] or 0) + (r["late"] or 0)
        rate  = round(100 * att / total, 1)
        courses.append(dict(r) | {"rate": rate})
        overall["present"] += r["present"] or 0
        overall["late"]    += r["late"] or 0
        overall["absent"]  += r["absent"] or 0
        overall["total"]   += r["total_sessions"] or 0

    ot = overall["total"] or 1
    overall["rate"] = round(100 * (overall["present"] + overall["late"]) / ot, 1)

    return render_template("student/dashboard.html", me=me, courses=courses, summary=overall)


@bp.route("/course/<int:cid>")
@stu_req
def course_detail(cid):
    me = _me()
    reg = q1("SELECT id FROM course_registrations WHERE course_id=? AND student_id=?", (cid, me["id"]))
    if not reg:
        abort(403)
    course = q1("SELECT c.*,u.full_name AS lecturer_name,l.title AS lec_title FROM courses c LEFT JOIN lecturers l ON l.id=c.lecturer_id LEFT JOIN users u ON u.id=l.user_id WHERE c.id=?", (cid,))
    rows = q("""SELECT cs.session_date, cs.start_time, cs.end_time, cs.venue, cs.room,
                cs.group_filter, cs.session_type,
                ar.status, ar.check_in_time, ar.minutes_late, ar.similarity_score, ar.source
                FROM class_sessions cs
                LEFT JOIN attendance_records ar ON ar.session_id=cs.id AND ar.student_id=?
                WHERE cs.course_id=?
                  AND (cs.group_filter IS NULL OR cs.group_filter=?)
                ORDER BY cs.session_date DESC""",
             (me["id"], cid, me["group_name"]))
    present = sum(1 for r in rows if (r["status"] or "absent") == "present")
    late    = sum(1 for r in rows if (r["status"] or "absent") == "late")
    total   = len(rows) or 1
    rate    = round(100 * (present + late) / total, 1)
    return render_template("student/course.html", me=me, course=course, rows=rows,
                           present=present, late=late, total=len(rows), rate=rate)


@bp.route("/consent", methods=["POST"])
@stu_req
def give_consent():
    me = _me()
    run("UPDATE students SET consent_given=1, consent_date=datetime('now') WHERE id=?", (me["id"],))
    flash("Biometric consent recorded. You are now eligible for FRT attendance.", "success")
    return redirect(url_for("student.dashboard"))


@bp.route("/consent/withdraw", methods=["POST"])
@stu_req
def withdraw_consent():
    me = _me()
    run("UPDATE students SET consent_given=0, enrolled_on_terminal=0 WHERE id=?", (me["id"],))
    flash("Consent withdrawn. Biometric data will be removed from the terminal.", "info")
    return redirect(url_for("student.dashboard"))

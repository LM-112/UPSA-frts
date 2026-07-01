from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, abort
from ..db import q, q1, run
from ..services.hik import HikvisionTerminal

bp = Blueprint("super_", __name__)


def super_req(f):
    @wraps(f)
    def d(*a, **kw):
        if session.get("user", {}).get("role") != "super":
            abort(403)
        return f(*a, **kw)
    return d


@bp.route("/")
@super_req
def dashboard():
    devices = q("SELECT * FROM hik_devices ORDER BY name")
    device_statuses = []
    for d in devices:
        term = HikvisionTerminal(d["ip_address"], simulate=True)
        info = term.get_device_info()
        device_statuses.append(dict(d) | {"online": bool(d["is_active"]), "info": info})

    stats = {
        "total_students": q1("SELECT COUNT(*) AS c FROM students")["c"],
        "total_faculties": q1("SELECT COUNT(*) AS c FROM faculties")["c"],
        "total_departments": q1("SELECT COUNT(*) AS c FROM departments")["c"],
        "total_courses": q1("SELECT COUNT(*) AS c FROM courses")["c"],
        "sessions_today": q1("SELECT COUNT(*) AS c FROM class_sessions WHERE session_date=date('now')")["c"],
        "enrolled": q1("SELECT COUNT(*) AS c FROM students WHERE enrolled_on_terminal=1")["c"],
    }
    faculties = q("""SELECT f.*, COUNT(DISTINCT d.id) AS dept_count,
                     COUNT(DISTINCT p.id) AS prog_count,
                     COUNT(DISTINCT s.id) AS student_count
                     FROM faculties f
                     LEFT JOIN departments d ON d.faculty_id=f.id
                     LEFT JOIN programmes p ON p.department_id=d.id
                     LEFT JOIN students s ON s.programme_id=p.id
                     GROUP BY f.id ORDER BY f.name""")
    enrolments = q("""SELECT el.*, u.full_name FROM enrollment_logs el
                      LEFT JOIN students s ON el.student_id=s.id
                      LEFT JOIN users u ON s.user_id=u.id
                      ORDER BY el.created_at DESC LIMIT 10""")
    events = q("SELECT * FROM event_logs ORDER BY occurred_at DESC LIMIT 10")
    users  = q("SELECT * FROM users ORDER BY role, full_name")
    return render_template("super/dashboard.html",
                           device_statuses=device_statuses, stats=stats,
                           faculties=faculties, enrolments=enrolments,
                           events=events, users=users)


@bp.route("/devices/register", methods=["GET", "POST"])
@super_req
def register_device():
    if request.method == "POST":
        run("INSERT INTO hik_devices(name,model,serial_no,ip_address,port,username,password,connection_type,wifi_ssid,room,is_active) VALUES(?,?,?,?,?,?,?,?,?,?,1)",
            (request.form.get("name"), request.form.get("model", "DS-K1T323MBFWX-E1"),
             request.form.get("serial_no"), request.form.get("ip_address"),
             int(request.form.get("port", 80)), request.form.get("username", "admin"),
             request.form.get("password"), request.form.get("connection_type", "wifi"),
             request.form.get("wifi_ssid"), request.form.get("room")))
        flash("Terminal registered successfully.", "success")
        return redirect(url_for("super_.dashboard"))
    return render_template("super/register_device.html")


@bp.route("/devices/<int:did>/probe")
@super_req
def probe_device(did):
    d = q1("SELECT * FROM hik_devices WHERE id=?", (did,))
    term = HikvisionTerminal(d["ip_address"], port=d["port"], username=d["username"],
                              password=d["password"] or "", simulate=True)
    info = term.get_device_info()
    if info:
        flash(f"Terminal online — {info['model']} SN:{info['serialNumber']}", "success")
    else:
        flash("Terminal unreachable. Check IP and credentials.", "danger")
    return redirect(url_for("super_.dashboard"))


@bp.route("/users")
@super_req
def users():
    users = q("SELECT * FROM users ORDER BY role, full_name")
    return render_template("super/users.html", users=users)


@bp.route("/faculties")
@super_req
def faculties():
    facs = q("SELECT f.*, COUNT(DISTINCT d.id) AS dept_count FROM faculties f LEFT JOIN departments d ON d.faculty_id=f.id GROUP BY f.id ORDER BY f.name")
    depts = q("SELECT d.*, f.id AS faculty_id FROM departments d JOIN faculties f ON f.id=d.faculty_id ORDER BY f.name, d.name")
    progs = q("SELECT p.*, d.id AS department_id FROM programmes p JOIN departments d ON d.id=p.department_id ORDER BY p.name")
    studs = q("SELECT s.*, p.department_id AS dept_id FROM students s LEFT JOIN programmes p ON p.id=s.programme_id")
    return render_template("super/faculties.html", faculties=facs, departments=depts, programmes=progs, students=studs)

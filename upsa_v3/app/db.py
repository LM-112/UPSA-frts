"""Lightweight SQLite helper — no Flask-SQLAlchemy dependency."""
import sqlite3
from pathlib import Path
from flask import g

DB_PATH = Path(__file__).resolve().parent.parent / "instance" / "upsa_frt.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()


def q(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def q1(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def run(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur.lastrowid


def init_schema():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _create_tables(conn)
    _seed(conn)
    conn.close()


def _create_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS faculties (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        code TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS departments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id INTEGER NOT NULL REFERENCES faculties(id),
        name       TEXT NOT NULL,
        code       TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS programmes (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER NOT NULL REFERENCES departments(id),
        name          TEXT NOT NULL,
        code          TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        email         TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name     TEXT NOT NULL,
        role          TEXT NOT NULL,
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT NOT NULL DEFAULT (datetime('now')),
        last_login_at TEXT
    );
    CREATE TABLE IF NOT EXISTS lecturers (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER NOT NULL UNIQUE REFERENCES users(id),
        staff_id      TEXT NOT NULL UNIQUE,
        title         TEXT,
        department_id INTEGER REFERENCES departments(id)
    );
    CREATE TABLE IF NOT EXISTS students (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id              INTEGER NOT NULL UNIQUE REFERENCES users(id),
        index_number         TEXT NOT NULL UNIQUE,
        employee_id          TEXT NOT NULL UNIQUE,
        programme_id         INTEGER REFERENCES programmes(id),
        level                INTEGER,
        group_name           TEXT,
        gender               TEXT,
        hall                 TEXT,
        consent_given        INTEGER NOT NULL DEFAULT 0,
        consent_date         TEXT,
        enrolled_on_terminal INTEGER NOT NULL DEFAULT 0,
        photo_path           TEXT,
        created_at           TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS courses (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        code          TEXT NOT NULL UNIQUE,
        title         TEXT NOT NULL,
        credit_hours  INTEGER NOT NULL DEFAULT 3,
        semester      INTEGER NOT NULL DEFAULT 2,
        academic_year TEXT NOT NULL DEFAULT '2025/2026',
        department_id INTEGER REFERENCES departments(id),
        lecturer_id   INTEGER REFERENCES lecturers(id)
    );
    CREATE TABLE IF NOT EXISTS course_registrations (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id  INTEGER NOT NULL REFERENCES courses(id),
        student_id INTEGER NOT NULL REFERENCES students(id),
        UNIQUE(course_id, student_id)
    );
    CREATE TABLE IF NOT EXISTS class_sessions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id    INTEGER NOT NULL REFERENCES courses(id),
        session_date TEXT NOT NULL,
        start_time   TEXT NOT NULL,
        end_time     TEXT NOT NULL,
        venue        TEXT,
        room         TEXT,
        group_filter TEXT,
        session_type TEXT DEFAULT 'regular',
        device_id    INTEGER REFERENCES hik_devices(id),
        is_open      INTEGER NOT NULL DEFAULT 0,
        notes        TEXT,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS attendance_records (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id       INTEGER NOT NULL REFERENCES class_sessions(id),
        student_id       INTEGER NOT NULL REFERENCES students(id),
        status           TEXT NOT NULL DEFAULT 'absent',
        check_in_time    TEXT,
        minutes_late     INTEGER DEFAULT 0,
        similarity_score REAL,
        source           TEXT DEFAULT 'terminal',
        note             TEXT,
        created_at       TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(session_id, student_id)
    );
    CREATE TABLE IF NOT EXISTS hik_devices (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        model           TEXT NOT NULL DEFAULT 'DS-K1T323MBFWX-E1',
        serial_no       TEXT,
        ip_address      TEXT NOT NULL,
        port            INTEGER NOT NULL DEFAULT 80,
        username        TEXT NOT NULL DEFAULT 'admin',
        password        TEXT,
        connection_type TEXT DEFAULT 'wifi',
        wifi_ssid       TEXT,
        room            TEXT,
        last_seen       TEXT,
        is_active       INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS enrollment_logs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id    INTEGER REFERENCES students(id),
        device_id     INTEGER REFERENCES hik_devices(id),
        action        TEXT,
        success       INTEGER DEFAULT 0,
        response_text TEXT,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS event_logs (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id        INTEGER REFERENCES hik_devices(id),
        employee_id_seen TEXT,
        similarity       REAL,
        occurred_at      TEXT NOT NULL DEFAULT (datetime('now')),
        raw_payload      TEXT,
        matched_session  INTEGER REFERENCES class_sessions(id),
        processed        INTEGER DEFAULT 0
    );
    """)
    conn.commit()


# ── Password helpers ──────────────────────────────────────────────────────────
from hashlib import pbkdf2_hmac
import os, binascii


def hash_pw(pw: str) -> str:
    salt = binascii.hexlify(os.urandom(16)).decode()
    dk = pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 260000)
    return f"pbkdf2:sha256:260000:{salt}:{binascii.hexlify(dk).decode()}"


def check_pw(stored: str, given: str) -> bool:
    try:
        _, _, iters, salt, hashed = stored.split(":")
        dk = pbkdf2_hmac("sha256", given.encode(), salt.encode(), int(iters))
        return binascii.hexlify(dk).decode() == hashed
    except Exception:
        return False


# ── Seed ─────────────────────────────────────────────────────────────────────
def _seed(conn):
    if conn.execute("SELECT id FROM users WHERE email='super@upsa.edu.gh'").fetchone():
        return  # already seeded

    import random
    from datetime import datetime as dt, timedelta as td

    random.seed(42)

    # Faculties
    for name, code in [
        ("Faculty of Information Technology & Communication Studies", "FoITCS"),
        ("Faculty of Management Studies", "FoMS"),
        ("Faculty of Accounting & Finance", "FoAF"),
    ]:
        conn.execute("INSERT INTO faculties(name,code) VALUES(?,?)", (name, code))

    f_it = conn.execute("SELECT id FROM faculties WHERE code='FoITCS'").fetchone()["id"]
    f_ms = conn.execute("SELECT id FROM faculties WHERE code='FoMS'").fetchone()["id"]
    f_af = conn.execute("SELECT id FROM faculties WHERE code='FoAF'").fetchone()["id"]

    # Departments
    depts = [
        ("Department of Information Technology Studies", "DITS", f_it),
        ("Department of Computer Science", "DCS", f_it),
        ("Department of Marketing", "DMKT", f_ms),
        ("Department of Management", "DMGT", f_ms),
        ("Department of Accounting", "DACC", f_af),
    ]
    for name, code, fid in depts:
        conn.execute("INSERT INTO departments(faculty_id,name,code) VALUES(?,?,?)", (fid, name, code))

    d_it  = conn.execute("SELECT id FROM departments WHERE code='DITS'").fetchone()["id"]
    d_mkt = conn.execute("SELECT id FROM departments WHERE code='DMKT'").fetchone()["id"]
    d_acc = conn.execute("SELECT id FROM departments WHERE code='DACC'").fetchone()["id"]

    # Programmes
    progs = [
        ("BSc Information Technology Management", "BITM", d_it),
        ("BSc Marketing", "BMK", d_mkt),
        ("BSc Accounting", "BACC", d_acc),
    ]
    for name, code, did in progs:
        conn.execute("INSERT INTO programmes(department_id,name,code) VALUES(?,?,?)", (did, name, code))

    p_it  = conn.execute("SELECT id FROM programmes WHERE code='BITM'").fetchone()["id"]
    p_mkt = conn.execute("SELECT id FROM programmes WHERE code='BMK'").fetchone()["id"]
    p_acc = conn.execute("SELECT id FROM programmes WHERE code='BACC'").fetchone()["id"]

    # Users
    def add_user(email, pw, role, name):
        conn.execute(
            "INSERT INTO users(email,password_hash,full_name,role,is_active) VALUES(?,?,?,?,1)",
            (email, hash_pw(pw), name, role)
        )
        return conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]

    add_user("super@upsa.edu.gh",  "Super@2026",    "super",    "System Super Admin")
    admin_id  = add_user("admin@upsa.edu.gh",  "Admin@2026",    "admin",    "Margaret Boadu")
    lec1_id   = add_user("kowusu@upsa.edu.gh", "Lecturer@2026", "lecturer", "Kwame Owusu")
    lec2_id   = add_user("aboateng@upsa.edu.gh","Lecturer@2026","lecturer", "Ama Boateng")
    lec3_id   = add_user("jmensah@upsa.edu.gh","Lecturer@2026", "lecturer", "James Mensah")

    # Lecturers
    conn.execute("INSERT INTO lecturers(user_id,staff_id,title,department_id) VALUES(?,?,?,?)",
                 (lec1_id, "UPSA/IT/0042", "Dr.", d_it))
    conn.execute("INSERT INTO lecturers(user_id,staff_id,title,department_id) VALUES(?,?,?,?)",
                 (lec2_id, "UPSA/MKT/0017","Dr.", d_mkt))
    conn.execute("INSERT INTO lecturers(user_id,staff_id,title,department_id) VALUES(?,?,?,?)",
                 (lec3_id, "UPSA/ACC/0031","Prof.",d_acc))

    lec1 = conn.execute("SELECT id FROM lecturers WHERE staff_id='UPSA/IT/0042'").fetchone()["id"]
    lec2 = conn.execute("SELECT id FROM lecturers WHERE staff_id='UPSA/MKT/0017'").fetchone()["id"]
    lec3 = conn.execute("SELECT id FROM lecturers WHERE staff_id='UPSA/ACC/0031'").fetchone()["id"]

    # Courses
    courses_data = [
        ("ITM 412","Information Systems Security",        3, d_it,  lec1),
        ("ITM 416","Mobile Application Development",     3, d_it,  lec1),
        ("ITM 408","Database Management Systems",        3, d_it,  lec1),
        ("ITM 404","Computer Networks",                  3, d_it,  lec1),
        ("ITM 402","Software Engineering",               3, d_it,  lec1),
        ("ITM 406","Artificial Intelligence",            3, d_it,  lec1),
        ("ITM 410","Cybersecurity Fundamentals",         3, d_it,  lec1),
        ("MKT 410","Digital Marketing Strategy",         3, d_mkt, lec2),
        ("MKT 414","Consumer Behaviour",                 3, d_mkt, lec2),
        ("MKT 406","Marketing Research",                 3, d_mkt, lec2),
        ("MKT 412","Strategic Marketing Management",     3, d_mkt, lec2),
        ("MKT 408","Brand Management",                   3, d_mkt, lec2),
        ("ACC 412","Financial Accounting",               3, d_acc, lec3),
        ("ACC 416","Auditing & Assurance",               3, d_acc, lec3),
        ("ACC 408","Management Accounting",              3, d_acc, lec3),
        ("ACC 410","Taxation & Revenue",                 3, d_acc, lec3),
    ]
    for code, title, cr, did, lid in courses_data:
        conn.execute("INSERT INTO courses(code,title,credit_hours,semester,academic_year,department_id,lecturer_id) VALUES(?,?,?,2,'2025/2026',?,?)",
                     (code, title, cr, did, lid))

    def cid(code):
        return conn.execute("SELECT id FROM courses WHERE code=?", (code,)).fetchone()["id"]

    # Device
    conn.execute("""INSERT INTO hik_devices(name,model,serial_no,ip_address,port,username,password,
                    connection_type,wifi_ssid,room,is_active) VALUES(?,?,?,?,?,?,?,?,?,?,1)""",
                 ("HIK-001","DS-K1T323MBFWX-E1","GM6647437","192.168.1.45",80,"admin","Upsa@2026",
                  "wifi","UPSA-Campus-WiFi","ITS Lab A"))
    dev = conn.execute("SELECT id FROM hik_devices LIMIT 1").fetchone()["id"]

    # Students — real + synthetic
    FIRST = ["Kwame","Akua","Yaw","Esi","Kofi","Ama","Kojo","Adwoa","Kwaku","Akosua",
             "Kwadwo","Afia","Yaa","Naa","Abena","Nana","Kweku","Mansa","Efua","Adjoa",
             "Kwesi","Adzo","Fiifi","Enyonam","Selorm","Elikplim","Delali","Dzifa"]
    LAST  = ["Mensah","Owusu","Asante","Boateng","Frimpong","Adjei","Annan","Quaye",
             "Tetteh","Darko","Agyemang","Osei","Bediako","Acheampong","Ofori","Sarpong",
             "Amoah","Twum","Kyei","Wiredu","Dzokoto","Ametsitsi","Gbadago","Tsidi"]
    HALLS = ["Yaa Asantewaa","Africa","Independence","Republic","Unity"]

    # Real student — Donkor Amponsah Lawrence
    real_uid = add_user("10300137@students.upsa.edu.gh","Student@2026","student","Donkor Amponsah Lawrence")
    conn.execute("""INSERT INTO students(user_id,index_number,employee_id,programme_id,level,
                    group_name,gender,hall,consent_given,consent_date,enrolled_on_terminal)
                    VALUES(?,?,?,?,?,?,?,?,1,datetime('now'),1)""",
                 (real_uid,"10300137","10300137",p_it,400,"IT1","male","Yaa Asantewaa"))
    real_st = conn.execute("SELECT id FROM students WHERE index_number='10300137'").fetchone()["id"]

    it_groups = ["IT1"]*20 + ["IT2"]*20 + ["IT3"]*20

    it_students_by_group = {"IT1": [], "IT2": [], "IT3": []}
    it_students_by_group["IT1"].append(real_st)

    for i in range(59):
        name  = f"{random.choice(FIRST)} {random.choice(LAST)}"
        idx   = f"1018{2700+i:04d}"
        uid   = add_user(f"{idx}@students.upsa.edu.gh","Student@2026","student",name)
        grp   = it_groups[i % len(it_groups)]
        conn.execute("""INSERT INTO students(user_id,index_number,employee_id,programme_id,level,
                        group_name,gender,hall,consent_given,consent_date,enrolled_on_terminal)
                        VALUES(?,?,?,?,?,?,?,?,1,datetime('now'),0)""",
                     (uid,idx,idx,p_it,400,grp,
                      random.choice(["male","female"]),random.choice(HALLS)))
        sid = conn.execute("SELECT id FROM students WHERE index_number=?", (idx,)).fetchone()["id"]
        it_students_by_group[grp].append(sid)

    mkt_students = []
    for i in range(45):
        name = f"{random.choice(FIRST)} {random.choice(LAST)}"
        idx  = f"1019{3000+i:04d}"
        uid  = add_user(f"{idx}@students.upsa.edu.gh","Student@2026","student",name)
        conn.execute("""INSERT INTO students(user_id,index_number,employee_id,programme_id,level,
                        group_name,gender,hall,consent_given,consent_date)
                        VALUES(?,?,?,?,?,?,?,?,1,datetime('now'))""",
                     (uid,idx,idx,p_mkt,300,"MKT1",random.choice(["male","female"]),random.choice(HALLS)))
        mkt_students.append(conn.execute("SELECT id FROM students WHERE index_number=?", (idx,)).fetchone()["id"])

    acc_students = []
    for i in range(25):
        name = f"{random.choice(FIRST)} {random.choice(LAST)}"
        idx  = f"1020{4000+i:04d}"
        uid  = add_user(f"{idx}@students.upsa.edu.gh","Student@2026","student",name)
        conn.execute("""INSERT INTO students(user_id,index_number,employee_id,programme_id,level,
                        group_name,gender,hall,consent_given,consent_date)
                        VALUES(?,?,?,?,?,?,?,?,1,datetime('now'))""",
                     (uid,idx,idx,p_acc,300,"ACC1",random.choice(["male","female"]),random.choice(HALLS)))
        acc_students.append(conn.execute("SELECT id FROM students WHERE index_number=?", (idx,)).fetchone()["id"])

    all_it = it_students_by_group["IT1"] + it_students_by_group["IT2"] + it_students_by_group["IT3"]

    # Course registrations
    for sid in all_it:
        for code in ["ITM 412","ITM 416","ITM 408","ITM 404","ITM 402","ITM 406","ITM 410"]:
            conn.execute("INSERT OR IGNORE INTO course_registrations(course_id,student_id) VALUES(?,?)",
                         (cid(code), sid))
    for sid in mkt_students:
        for code in ["MKT 410","MKT 414","MKT 406","MKT 412","MKT 408"]:
            conn.execute("INSERT OR IGNORE INTO course_registrations(course_id,student_id) VALUES(?,?)",
                         (cid(code), sid))
    for sid in acc_students:
        for code in ["ACC 412","ACC 416","ACC 408","ACC 410"]:
            conn.execute("INSERT OR IGNORE INTO course_registrations(course_id,student_id) VALUES(?,?)",
                         (cid(code), sid))

    # Sessions: group-split timetable
    # IT1 — Monday 07:30-10:30, IT2 — Friday 11:00-14:00, IT3 — Wednesday 14:15-17:15
    VENUES = {
        "LBC 301": ("LBC", "301"),
        "LBC 506": ("LBC", "506"),
        "LBC 201": ("LBC", "201"),
        "SCH 401": ("Student Centre", "SCH 401"),
        "GS-A":    ("Graduate School", "GS-A"),
    }

    today = dt.now()

    def make_sessions(course_code, group, weekday_offset_pattern, start_h, start_m, end_h, end_m, venue_key, stype="regular"):
        venue, room = VENUES[venue_key]
        for week in range(-3, 1):  # 3 past weeks + this week
            for day_off in weekday_offset_pattern:
                base = today - td(days=today.weekday()) + td(days=day_off) + td(weeks=week)
                if base.date() > today.date():
                    continue
                sd = base.strftime("%Y-%m-%d")
                conn.execute("""INSERT INTO class_sessions(course_id,session_date,start_time,end_time,
                                venue,room,group_filter,session_type,device_id,is_open)
                                VALUES(?,?,?,?,?,?,?,?,?,0)""",
                             (cid(course_code), sd,
                              f"{start_h:02d}:{start_m:02d}",
                              f"{end_h:02d}:{end_m:02d}",
                              venue, room, group, stype, dev))

    # IT1 — Monday = 0
    make_sessions("ITM 412","IT1",[0], 7,30,10,30,"LBC 301")
    make_sessions("ITM 416","IT1",[2], 7,30,10,30,"LBC 506")
    make_sessions("ITM 408","IT1",[4], 11,0,14,0, "SCH 401")
    make_sessions("ITM 404","IT1",[1], 14,15,17,15,"LBC 201")
    make_sessions("ITM 402","IT1",[3], 11,0,14,0,  "LBC 506")
    make_sessions("ITM 406","IT1",[4], 14,15,17,15,"GS-A")
    make_sessions("ITM 410","IT1",[2], 14,15,17,15,"LBC 301")

    # IT2 — Friday = 4
    make_sessions("ITM 412","IT2",[4], 11,0,14,0, "LBC 506")
    make_sessions("ITM 416","IT2",[0], 14,15,17,15,"LBC 301")
    make_sessions("ITM 408","IT2",[2], 7,30,10,30, "SCH 401")
    make_sessions("ITM 404","IT2",[3], 11,0,14,0,  "LBC 201")
    make_sessions("ITM 402","IT2",[1], 7,30,10,30, "LBC 201")
    make_sessions("ITM 406","IT2",[4], 7,30,10,30, "GS-A")
    make_sessions("ITM 410","IT2",[0], 11,0,14,0,  "LBC 506")

    # IT3 — Wednesday = 2
    make_sessions("ITM 412","IT3",[2], 14,15,17,15,"GS-A")
    make_sessions("ITM 416","IT3",[4], 7,30,10,30, "LBC 201")
    make_sessions("ITM 408","IT3",[0], 11,0,14,0,  "LBC 301")
    make_sessions("ITM 404","IT3",[3], 14,15,17,15,"LBC 506")
    make_sessions("ITM 402","IT3",[2], 7,30,10,30, "LBC 506")
    make_sessions("ITM 406","IT3",[1], 14,15,17,15,"LBC 201")
    make_sessions("ITM 410","IT3",[3], 7,30,10,30, "GS-A")

    # Marketing
    make_sessions("MKT 410","MKT1",[1], 7,30,10,30,"LBC 201")
    make_sessions("MKT 414","MKT1",[3], 11,0,14,0, "SCH 401")
    make_sessions("MKT 406","MKT1",[5], 8,0,16,0,  "GS-A","weekend")
    make_sessions("MKT 412","MKT1",[0], 14,15,17,15,"LBC 506")
    make_sessions("MKT 408","MKT1",[2], 11,0,14,0,  "LBC 201")

    # Accounting
    make_sessions("ACC 412","ACC1",[1], 17,0,20,0, "GS-A","evening")
    make_sessions("ACC 416","ACC1",[3], 17,0,20,0, "LBC 301","evening")
    make_sessions("ACC 408","ACC1",[0], 17,0,20,0, "LBC 506","evening")
    make_sessions("ACC 410","ACC1",[4], 17,0,20,0, "SCH 401","evening")

    conn.commit()

    # Live demo session — always active right now
    now_start = (today - td(minutes=15)).strftime("%Y-%m-%d %H:%M")
    now_end   = (today + td(hours=2)).strftime("%Y-%m-%d %H:%M")
    conn.execute("""INSERT INTO class_sessions(course_id,session_date,start_time,end_time,
                    venue,room,group_filter,device_id,is_open,notes)
                    VALUES(?,?,?,?,?,?,?,?,1,?)""",
                 (cid("ITM 412"), today.strftime("%Y-%m-%d"),
                  (today - td(minutes=15)).strftime("%H:%M"),
                  (today + td(hours=2)).strftime("%H:%M"),
                  "LBC", "301", "IT1", dev,
                  "Live demo session — auto-generated for defence"))
    live_sess = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    conn.commit()

    # Attendance records for past sessions
    all_past = conn.execute("""SELECT id, course_id, session_date, start_time, group_filter
                               FROM class_sessions WHERE session_date < date('now')""").fetchall()
    statuses = ["present","present","present","late","absent","present","present","late","present","absent"]

    for s in all_past:
        grp = s["group_filter"]
        if grp and grp.startswith("IT"):
            roster = it_students_by_group.get(grp, [])
        elif grp and grp.startswith("MKT"):
            roster = mkt_students
        elif grp and grp.startswith("ACC"):
            roster = acc_students
        else:
            roster = all_it
        h, m = int(s["start_time"][:2]), int(s["start_time"][3:5])
        for i, stu in enumerate(roster):
            status = statuses[i % len(statuses)]
            if status == "absent":
                conn.execute("""INSERT OR IGNORE INTO attendance_records
                                (session_id,student_id,status,minutes_late)
                                VALUES(?,?,?,0)""", (s["id"], stu, "absent"))
            else:
                mins_late = random.randint(16, 28) if status == "late" else 0
                cin_m = m + mins_late + random.randint(0, 5)
                cin_h = h + cin_m // 60
                cin_m = cin_m % 60
                cin_str = f"{s['session_date']} {cin_h:02d}:{cin_m:02d}:00"
                sim = round(random.uniform(0.87, 0.99), 3)
                conn.execute("""INSERT OR IGNORE INTO attendance_records
                                (session_id,student_id,status,check_in_time,minutes_late,similarity_score)
                                VALUES(?,?,?,?,?,?)""",
                             (s["id"], stu, status, cin_str, mins_late, sim))

    # Mark some students present in live demo
    for i, stu in enumerate(it_students_by_group["IT1"][:10]):
        status = "present" if i < 7 else "late"
        ml = 0 if status == "present" else random.randint(16,25)
        cin_str = (today - td(minutes=14-ml)).strftime("%Y-%m-%d %H:%M:%S")
        sim = round(random.uniform(0.88, 0.99), 3)
        conn.execute("""INSERT OR IGNORE INTO attendance_records
                        (session_id,student_id,status,check_in_time,minutes_late,similarity_score)
                        VALUES(?,?,?,?,?,?)""", (live_sess, stu, status, cin_str, ml, sim))

    conn.commit()
    print("✓ Database seeded successfully")
    print("  Faculties: 3  |  Departments: 5  |  Programmes: 3")
    print("  Students: IT(60) + MKT(45) + ACC(25) = 130")
    print("  Courses: 16  |  Groups: IT1 IT2 IT3 MKT1 ACC1")

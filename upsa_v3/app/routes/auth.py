from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from ..db import q1, run

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw    = request.form.get("password", "")
        user  = q1("SELECT * FROM users WHERE email=? AND is_active=1", (email,))
        if user:
            from ..db import check_pw
            if check_pw(user["password_hash"], pw):
                run("UPDATE users SET last_login_at=datetime('now') WHERE id=?", (user["id"],))
                session.permanent = True
                session["user"] = {"id": user["id"], "email": user["email"],
                                   "full_name": user["full_name"], "role": user["role"]}
                role = user["role"]
                if role == "super":
                    return redirect(url_for("super_.dashboard"))
                return redirect(url_for(f"{role}.dashboard"))
        error = "Invalid email or password."
    return render_template("auth/login.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))

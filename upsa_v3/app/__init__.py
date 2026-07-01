import os
from flask import Flask, redirect, url_for, session
from .db import init_schema, close_db


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("SECRET_KEY", "upsa-frt-2026-dev-key")

    app.config.update(
        INSTITUTION_NAME="University of Professional Studies, Accra",
        INSTITUTION_SHORT="UPSA",
        ACADEMIC_YEAR="2025/2026",
        HIK_IP=os.getenv("HIK_IP", "192.168.1.45"),
        HIK_PORT=int(os.getenv("HIK_PORT", "80")),
        HIK_USER=os.getenv("HIK_USER", "admin"),
        HIK_PASS=os.getenv("HIK_PASS", "Upsa@2026"),
        HIK_SIMULATE=os.getenv("HIK_SIMULATE", "1") == "1",
    )

    with app.app_context():
        init_schema()

    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_globals():
        return {
            "INSTITUTION_NAME": app.config["INSTITUTION_NAME"],
            "INSTITUTION_SHORT": app.config["INSTITUTION_SHORT"],
            "ACADEMIC_YEAR": app.config["ACADEMIC_YEAR"],
            "current_user": session.get("user"),
        }

    from .routes.auth     import bp as auth_bp
    from .routes.super_   import bp as super_bp
    from .routes.admin    import bp as admin_bp
    from .routes.lecturer import bp as lecturer_bp
    from .routes.student  import bp as student_bp
    from .routes.api      import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(super_bp,    url_prefix="/super")
    app.register_blueprint(admin_bp,    url_prefix="/admin")
    app.register_blueprint(lecturer_bp, url_prefix="/lecturer")
    app.register_blueprint(student_bp,  url_prefix="/student")
    app.register_blueprint(api_bp,      url_prefix="/api/v1")

    @app.route("/")
    def index():
        u = session.get("user")
        if not u:
            return redirect(url_for("auth.login"))
        role = u["role"]
        if role == "super":
            return redirect(url_for("super_.dashboard"))
        return redirect(url_for(f"{role}.dashboard"))

    return app

"""GITHUB Event Registration Portal - Flask + SQLite backend."""
import csv, hmac, io, os, re, secrets, sqlite3, time, uuid
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
DB_PATH = os.path.join(BASE, "portal.db")
UPLOAD_DIR = os.path.join(BASE, "uploads")
IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
DOC_EXT = {"pdf", "doc", "docx", "ppt", "pptx"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@student\.gitam\.edu$", re.I)
BRANCHES = ["CSE-AIML", "CSE", "ECE", "EEE", "Mechanical", "Civil", "Other"]
YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]

# Secrets come from .env (see setup_env.py). The password is stored only as a salted hash.
ADMIN_USER = os.environ.get("ADMIN_USER", "").strip().lower()
ADMIN_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not (ADMIN_USER and ADMIN_HASH and SECRET_KEY):
    raise SystemExit("Missing .env settings. Run: python setup_env.py")
FAILS = {}  # ip -> recent failed login times (simple brute-force throttle)
MAX_FAILS, LOCK_SECONDS = 5, 900

app = Flask(__name__, template_folder=BASE, static_folder=None)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB upload limit
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    DB_PATH=DB_PATH,
)
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.route("/static/<path:filename>", endpoint="static")
def static_asset(filename):
    if filename not in {"style.css", "app.js", "admin.js"}:
        abort(404)
    return send_from_directory(BASE, filename)


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, image TEXT,
  event_date TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL,
  location TEXT NOT NULL, description TEXT DEFAULT '', document TEXT,
  status TEXT NOT NULL DEFAULT 'Live' CHECK (status IN ('Live','Closed')),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS registrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name TEXT NOT NULL, gitam_mail TEXT NOT NULL, branch TEXT NOT NULL,
  year TEXT NOT NULL, rollno TEXT NOT NULL, qr_token TEXT NOT NULL UNIQUE,
  checked_in INTEGER NOT NULL DEFAULT 0,
  registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (event_id, rollno));
"""


def db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(app.config["DB_PATH"])
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


@app.template_filter("fdate")
def fdate(v):
    try:
        return datetime.strptime(v, "%Y-%m-%d").strftime("%a, %d %b %Y")
    except (ValueError, TypeError):
        return v


@app.template_filter("ftime")
def ftime(v):
    try:
        return datetime.strptime(v, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return v


def reg_code(r):
    return f"GH-{r['event_id']}-{r['id']:05d}"


app.jinja_env.globals["reg_code"] = reg_code


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            if request.path.startswith("/admin/api"):
                return jsonify(status="error", message="Please log in as admin."), 401
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


def save_upload(file, allowed):
    """Returns (filename|None, error|None). Validates extension on the server."""
    if not file or not file.filename:
        return None, None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        return None, f"Allowed file types: {', '.join(sorted(allowed))}."
    name = f"{uuid.uuid4().hex[:12]}_{secure_filename(file.filename)}"
    file.save(os.path.join(UPLOAD_DIR, name))
    return name, None


def remove_file(name):
    if name:
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass


# ---------------------------------------------------------------- public pages
@app.route("/")
def index():
    events = db().execute(
        "SELECT * FROM events ORDER BY event_date, start_time").fetchall()
    live = sum(1 for e in events if e["status"] == "Live")
    return render_template("index.html", events=events, live=live)


@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/register")
def register_list():
    return redirect(url_for("index") + "#registration")


@app.route("/register/<int:event_id>", methods=["GET", "POST"])
def register(event_id):
    event = db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        abort(404)
    form, errors = request.form, []
    if request.method == "POST":
        name = form.get("name", "").strip()
        mail = form.get("gitam_mail", "").strip().lower()
        branch, year = form.get("branch", ""), form.get("year", "")
        rollno = form.get("rollno", "").strip().upper()
        if event["status"] != "Live":
            errors.append("Registration Closed for this event.")
        if not all([name, mail, branch, year, rollno]):
            errors.append("All fields are required.")
        if mail and not EMAIL_RE.match(mail):
            errors.append("Use your GITAM email ending in @student.gitam.edu.")
        if branch and branch not in BRANCHES:
            errors.append("Choose a valid branch.")
        if year and year not in YEARS:
            errors.append("Choose a valid year of study.")
        if rollno and not re.fullmatch(r"[A-Z0-9/-]{4,20}", rollno):
            errors.append("Registration number must be 4-20 letters or digits.")
        if not errors:
            token = secrets.token_urlsafe(16)
            try:
                db().execute(
                    "INSERT INTO registrations (event_id,name,gitam_mail,branch,year,rollno,qr_token)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (event_id, name, mail, branch, year, rollno, token))
                db().commit()
                return redirect(url_for("success", token=token))
            except sqlite3.IntegrityError:
                errors.append("This registration number is already registered for this event.")
    return render_template("register.html", event=event, events=None,
                           errors=errors, form=form, branches=BRANCHES, years=YEARS)


@app.route("/success/<token>")
def success(token):
    row = db().execute(
        "SELECT r.*, e.name AS event_name, e.event_date, e.start_time, e.end_time, e.location "
        "FROM registrations r JOIN events e ON e.id=r.event_id WHERE r.qr_token=?",
        (token,)).fetchone()
    if not row:
        abort(404)
    return render_template("success.html", r=row)


# ---------------------------------------------------------------- admin auth
@app.route("/admin/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("username", "").strip().lower()
        pw = request.form.get("password", "")
        ip, now = request.remote_addr, time.time()
        FAILS[ip] = [t for t in FAILS.get(ip, []) if now - t < LOCK_SECONDS]
        if not EMAIL_RE.match(user):
            error = "Enter   a valid GITAM student email ending in @student.gitam.edu."
        elif len(FAILS[ip]) >= MAX_FAILS:
            error = "Too many failed attempts. Try again in 15 minutes."
        else:
            user_ok = hmac.compare_digest(user.encode(), ADMIN_USER.encode())
            pw_ok = check_password_hash(ADMIN_HASH, pw)  # always run, so timing doesn't reveal the user
            if not (user_ok and pw_ok):
                FAILS[ip].append(now)
                error = "Invalid credentials."
            else:
                FAILS.pop(ip, None)
                session.clear()
                session["admin"] = user
                return redirect(url_for("admin"))
    return render_template("login.html", error=error)


@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------- admin dashboard
@app.route("/admin")
@admin_required
def admin():
    d = db()
    events = [dict(r) for r in d.execute(
        "SELECT * FROM events ORDER BY event_date DESC, start_time")]
    regs = d.execute(
        "SELECT r.*, e.name AS event_name FROM registrations r "
        "JOIN events e ON e.id=r.event_id ORDER BY r.registered_at DESC").fetchall()
    reg_list = [dict(event_id=r["event_id"], event=r["event_name"], name=r["name"],
                     rollno=r["rollno"], checked=bool(r["checked_in"])) for r in regs]
    stats = dict(events=len(events), regs=len(regs),
                 checked=sum(r["checked_in"] for r in regs))
    cfg = {k: os.environ.get(k, "") for k in
           ("EMAILJS_SERVICE_ID", "EMAILJS_TEMPLATE_ID", "EMAILJS_PUBLIC_KEY")}
    return render_template("admin.html", events=events, regs=regs, reg_list=reg_list, stats=stats, cfg=cfg)


@app.route("/admin/events/save", methods=["POST"])
@admin_required
def save_event():
    f = request.form
    event_id = f.get("id", type=int)
    old = None
    if event_id:
        old = db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not old:
            abort(404)
    name, date = f.get("name", "").strip(), f.get("event_date", "").strip()
    start, end = f.get("start_time", "").strip(), f.get("end_time", "").strip()
    loc, desc = f.get("location", "").strip(), f.get("description", "").strip()
    status = f.get("status", "Live")
    errs = []
    if not all([name, date, start, end, loc]):
        errs.append("Name, date, start time, end time and location are required.")
    try:
        datetime.strptime(date, "%Y-%m-%d")
        datetime.strptime(start, "%H:%M"); datetime.strptime(end, "%H:%M")
        if end <= start:
            errs.append("End time must be after start time.")
    except ValueError:
        errs.append("Enter a valid date and times.")
    if status not in ("Live", "Closed"):
        errs.append("Status must be Live or Closed.")
    image, e1 = save_upload(request.files.get("image"), IMG_EXT)
    doc, e2 = save_upload(request.files.get("document"), DOC_EXT)
    errs += [e for e in (e1, e2) if e]
    if errs:
        remove_file(image); remove_file(doc)
        for e in errs:
            flash(e, "error")
        return redirect(url_for("admin"))
    d = db()
    if old:
        if image: remove_file(old["image"])
        if doc: remove_file(old["document"])
        d.execute("UPDATE events SET name=?,image=?,event_date=?,start_time=?,end_time=?,"
                  "location=?,description=?,document=?,status=? WHERE id=?",
                  (name, image or old["image"], date, start, end, loc, desc,
                   doc or old["document"], status, event_id))
        flash("Event updated.", "success")
    else:
        d.execute("INSERT INTO events (name,image,event_date,start_time,end_time,location,"
                  "description,document,status) VALUES (?,?,?,?,?,?,?,?,?)",
                  (name, image, date, start, end, loc, desc, doc, status))
        flash("Event created.", "success")
    d.commit()
    return redirect(url_for("admin"))


@app.route("/admin/events/<int:event_id>/status", methods=["POST"])
@admin_required
def toggle_status(event_id):
    db().execute("UPDATE events SET status = CASE status WHEN 'Live' THEN 'Closed' ELSE 'Live' END "
                 "WHERE id=?", (event_id,))
    db().commit()
    flash("Event status changed.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@admin_required
def delete_event(event_id):
    ev = db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if ev:
        db().execute("DELETE FROM events WHERE id=?", (event_id,))  # registrations cascade
        db().commit()
        remove_file(ev["image"]); remove_file(ev["document"])
        flash("Event and its registrations removed.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/export.csv")
@admin_required
def export_csv():
    event_id = request.args.get("event_id", type=int)
    q = ("SELECT e.name, r.name, r.gitam_mail, r.branch, r.year, r.rollno, r.registered_at, "
         "r.checked_in FROM registrations r JOIN events e ON e.id=r.event_id")
    rows = db().execute(q + (" WHERE e.id=?" if event_id else "") + " ORDER BY e.name, r.name",
                        (event_id,) if event_id else ()).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Event", "Name", "GITAM Email", "Branch", "Year", "Roll No",
                "Registered At", "Checked In"])
    for r in rows:
        w.writerow([*list(r)[:-1], "Yes" if r[-1] else "No"])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=registrations.csv"})


@app.route("/admin/api/checkin", methods=["POST"])
@admin_required
def checkin():
    data = request.get_json(silent=True) or {}
    token, rollno = str(data.get("token", "")).strip(), str(data.get("rollno", "")).strip().upper()
    base = ("SELECT r.*, e.name AS event_name FROM registrations r "
            "JOIN events e ON e.id=r.event_id WHERE ")
    if token:
        row = db().execute(base + "r.qr_token=?", (token,)).fetchone()
    elif rollno and data.get("event_id"):
        row = db().execute(base + "r.rollno=? AND r.event_id=?",
                           (rollno, int(data["event_id"]))).fetchone()
    else:
        return jsonify(status="error", message="Provide a QR token, or a roll number and event."), 400
    if not row:
        return jsonify(status="notfound", message="Registration not found."), 404
    info = dict(name=row["name"], rollno=row["rollno"], event=row["event_name"],
                event_id=row["event_id"])
    if row["checked_in"]:
        return jsonify(status="already", message="Already checked in.", **info)
    db().execute("UPDATE registrations SET checked_in=1 WHERE id=?", (row["id"],))
    db().commit()
    return jsonify(status="ok", message="Check-in successful.", **info)


@app.errorhandler(413)
def too_large(_):
    flash("File too large (max 10 MB).", "error")
    return redirect(url_for("admin"))


@app.errorhandler(404)
def not_found(_):
    return render_template("base.html", not_found=True), 404


init_db()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")

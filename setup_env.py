"""Create or update .env: hashed admin password + fresh SECRET_KEY.

Run:  python setup_env.py
The password is never stored in plain text, only its salted scrypt hash.
"""
import getpass, os, re, secrets, sys
from werkzeug.security import generate_password_hash

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@student\.gitam\.edu$", re.I)
DEFAULTS = {"EMAILJS_SERVICE_ID": "", "EMAILJS_TEMPLATE_ID": "", "EMAILJS_PUBLIC_KEY": "",
            "COOKIE_SECURE": "0"}  # set COOKIE_SECURE=1 when serving over HTTPS


def is_strong(pw):
    return (len(pw) >= 12 and re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw)
            and re.search(r"\d", pw) and re.search(r"[^A-Za-z0-9]", pw))


def read_env():
    vals = {}
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                vals[k.strip()] = v.strip().strip("'\"")
    return vals


def write_env(user, password):
    vals = {**DEFAULTS, **read_env()}
    vals["ADMIN_USER"] = user.strip().lower()
    vals["ADMIN_PASSWORD_HASH"] = generate_password_hash(password)
    vals["SECRET_KEY"] = secrets.token_hex(32)  # new key also logs out old sessions
    order = ["ADMIN_USER", "ADMIN_PASSWORD_HASH", "SECRET_KEY"] + [k for k in vals if k not in
             ("ADMIN_USER", "ADMIN_PASSWORD_HASH", "SECRET_KEY")]
    with open(ENV, "w", encoding="utf-8") as f:
        f.write("# Private settings. Never commit or share this file.\n")
        for k in order:
            f.write(f"{k}='{vals[k]}'\n")  # single quotes keep '$' in the hash literal
    try:
        os.chmod(ENV, 0o600)
    except OSError:
        pass


if __name__ == "__main__":
    cur = read_env().get("ADMIN_USER", "gteddi@student.gitam.edu")
    user = input(f"Admin GITAM email [{cur}]: ").strip() or cur
    if not EMAIL_RE.match(user):
        sys.exit("Use an email ending in @student.gitam.edu.")
    pw = getpass.getpass("New admin password: ")
    if not is_strong(pw):
        sys.exit("Password needs 12+ characters with upper, lower, a digit and a symbol.")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    write_env(user, pw)
    print("Saved .env. Restart the server to apply it.")

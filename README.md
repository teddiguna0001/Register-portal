# GITHUB Event Registration Portal

Flask + SQLite + vanilla JS portal for GITAM student events: event CRUD, per-event registration, QR check-in, CSV export, email.

## Run locally
1. Install Python 3.10+ from python.org (tick "Add to PATH" on Windows).
2. Create a virtual environment: `python -m venv venv`, then `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (macOS/Linux).
3. Install dependencies and start the server:
```bash
pip install -r requirements.txt
python app.py
```
4. Open http://127.0.0.1:5000. `portal.db` is created automatically on first run.

## Use it
- **Admin login:** click Admin Login. The demo account is `gteddi@student.gitam.edu` with the demo password from the project brief. Change it right away (see below).
- **Events:** Dashboard > Events > Add Event. Edit keeps existing files if you upload none. Click the Live/Closed badge to switch status. Remove deletes the event and its registrations.
- **Student registration:** Registration (or Register Now on a card) > fill the form > success page shows the QR code with a download button.
- **Check-in:** Dashboard > QR check-in. Start the camera and scan, or enter the roll number manually and choose the event. Camera needs permission and HTTPS (localhost works).
- **CSV:** Dashboard > Registrations > Export CSV (follows the event filter).

## Admin password and .env
All secrets live in `.env` (already git-ignored): `ADMIN_USER`, `ADMIN_PASSWORD_HASH`, `SECRET_KEY`, plus the EmailJS values. The password is stored only as a salted scrypt hash, never in plain text, and no password appears in the code.
- Set a new password: `python setup_env.py` (needs 12+ characters with upper, lower, digit and symbol). It also rotates `SECRET_KEY`, which logs out existing sessions. Restart the server afterwards.
- If `.env` is missing the app stops and tells you to run `setup_env.py`. `.env.example` shows the format.
- Five wrong passwords from one address lock login for 15 minutes.
- Treat `.env` like a password: never commit or share it, and back up `portal.db` separately.

## Email
Without configuration the Email button opens your mail app via `mailto:`. For EmailJS:
1. Create an account at emailjs.com, add an Email Service (Gmail etc.) and copy its **Service ID**.
2. Create a template using variables `{{to_email}}`, `{{subject}}`, `{{message}}`, `{{event_name}}`; copy the **Template ID**.
3. Copy your **Public Key** from Account > General.
4. Put `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID`, `EMAILJS_PUBLIC_KEY` in `.env`, then restart. These three values are designed to be public; never put a private key in the frontend. Bulk email is not included (it needs a confirmation step and rate-limit handling).

## Deploy
Use a host with a persistent disk (Render, Railway, PythonAnywhere, a VPS) and run `gunicorn app:app`.
Before going live: serve over HTTPS; put `ADMIN_USER`, `ADMIN_PASSWORD_HASH` and `SECRET_KEY` (from `setup_env.py`) in your host's secret/environment settings and set `COOKIE_SECURE=1` once HTTPS is on; add CSRF protection (e.g. Flask-WTF); keep `portal.db` and `uploads/` on persistent storage with regular backups; debug mode is already off unless `FLASK_DEBUG=1`; consider scanning uploads and serving them from object storage.

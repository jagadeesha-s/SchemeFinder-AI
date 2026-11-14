"""Sign up / sign in with email OTP + saved applications (SQLite)."""
import hashlib
import hmac
import re
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage

import config

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _conn() -> sqlite3.Connection:
    config.USERS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.USERS_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS otps (
            email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, purpose TEXT NOT NULL,
            name TEXT, expires_at REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            sent_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, scheme_name TEXT NOT NULL,
            official_url TEXT, status TEXT NOT NULL, updated_at REAL NOT NULL,
            UNIQUE(email, scheme_name));
        """
    )
    return conn


def _hash(email: str, code: str) -> str:
    return hmac.new(config.APP_SECRET.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def _send_email(to: str, code: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = "Your SchemeFinder AI verification code"
    msg["From"] = config.SMTP_FROM
    msg["To"] = to
    msg.set_content(
        f"Your SchemeFinder AI one-time password (OTP) is: {code}\n\n"
        f"It is valid for {config.OTP_TTL_SECONDS // 60} minutes. Do not share it with anyone."
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


def request_otp(email: str, purpose: str, name: str = "") -> tuple[bool, str, str | None]:
    """purpose: 'signup' or 'signin'. Returns (ok, message, dev_otp_or_None)."""
    email = (email or "").strip().lower()
    name = (name or "").strip()
    if not valid_email(email):
        return False, "Please enter a valid email address.", None
    if purpose == "signup" and len(name) < 2:
        return False, "Please enter your full name.", None

    with _conn() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
        if purpose == "signup" and exists:
            return False, "This email is already registered. Please use Sign In.", None
        if purpose == "signin" and not exists:
            return False, "No account found for this email. Please Sign Up first.", None

        row = conn.execute("SELECT sent_at FROM otps WHERE email=?", (email,)).fetchone()
        if row and time.time() - row["sent_at"] < config.OTP_RESEND_SECONDS:
            wait = int(config.OTP_RESEND_SECONDS - (time.time() - row["sent_at"]))
            return False, f"Please wait {wait} seconds before requesting another OTP.", None

        code = "".join(str(secrets.randbelow(10)) for _ in range(config.OTP_LENGTH))
        now = time.time()
        conn.execute(
            "INSERT OR REPLACE INTO otps(email, code_hash, purpose, name, expires_at, attempts, sent_at) "
            "VALUES (?,?,?,?,?,0,?)",
            (email, _hash(email, code), purpose, name, now + config.OTP_TTL_SECONDS, now),
        )

    if config.SMTP_CONFIGURED:
        try:
            _send_email(email, code)
        except Exception as exc:
            return False, f"Could not send the email: {exc}", None
        return True, f"We sent a {config.OTP_LENGTH}-digit OTP to {email}.", None
    if config.DEV_SHOW_OTP:
        return True, "Email is not configured, so demo mode is on.", code
    return False, "Email sending is not configured. Ask the administrator to set SMTP in .env.", None


def verify_otp(email: str, code: str, purpose: str) -> tuple[bool, str, dict | None]:
    email = (email or "").strip().lower()
    code = (code or "").strip()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM otps WHERE email=? AND purpose=?", (email, purpose)).fetchone()
        if not row:
            return False, "Please request an OTP first.", None
        if time.time() > row["expires_at"]:
            conn.execute("DELETE FROM otps WHERE email=?", (email,))
            return False, "This OTP has expired. Please request a new one.", None
        if row["attempts"] >= config.OTP_MAX_ATTEMPTS:
            conn.execute("DELETE FROM otps WHERE email=?", (email,))
            return False, "Too many wrong attempts. Please request a new OTP.", None
        if not hmac.compare_digest(row["code_hash"], _hash(email, code)):
            conn.execute("UPDATE otps SET attempts = attempts + 1 WHERE email=?", (email,))
            return False, "Incorrect OTP. Please try again.", None

        conn.execute("DELETE FROM otps WHERE email=?", (email,))
        if purpose == "signup":
            conn.execute(
                "INSERT OR IGNORE INTO users(email, name, created_at) VALUES (?,?,?)",
                (email, row["name"], time.time()),
            )
        user = conn.execute("SELECT email, name FROM users WHERE email=?", (email,)).fetchone()
        return True, "Verified successfully.", dict(user)


# ---------------------------------------------------------- applications
def save_application(email: str, scheme_name: str, official_url: str | None,
                     status: str = "Application started (self-reported)") -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO applications(email, scheme_name, official_url, status, updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(email, scheme_name) DO UPDATE SET status=excluded.status, "
            "official_url=excluded.official_url, updated_at=excluded.updated_at",
            (email, scheme_name, official_url or "", status, time.time()),
        )


def list_applications(email: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT scheme_name, official_url, status FROM applications WHERE email=? ORDER BY updated_at DESC",
            (email,),
        ).fetchall()
    return [dict(r) for r in rows]

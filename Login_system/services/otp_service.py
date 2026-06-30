"""OTP persistence + email delivery service for the login system.

Extracted verbatim from ``login_server.py`` during the Phase 3 refactor.
Business logic only; persistence goes through the repository connection factory
and hashing through the utils layer. No login_server module globals are used.
"""
from datetime import datetime, timedelta

import requests

from config import (
    EMAILJS_PUBLIC_KEY,
    EMAILJS_PRIVATE_KEY,
    EMAILJS_SERVICE_ID,
    EMAILJS_TEMPLATE_ID,
)
from Login_system.repositories.db import get_db
from Login_system.utils.otp import hash_otp, verify_otp_hash


def store_otp(email: str, otp_code: str, temp_user_data: str):
    """Store OTP in database with expiration."""
    conn = get_db()
    c = conn.cursor()

    # Delete old OTPs for this email
    c.execute("DELETE FROM otp_verification WHERE email=?", (email,))

    # Store new OTP (expires in 10 minutes)
    expires_at = datetime.now() + timedelta(minutes=10)
    # Hash OTP before storing
    otp_hash = hash_otp(otp_code)
    c.execute("""
        INSERT INTO otp_verification (email, otp_code, expires_at, temp_user_data, purpose)
        VALUES (?, ?, ?, ?, 'registration')
    """, (email, otp_hash, expires_at, temp_user_data))

    conn.commit()
    conn.close()


def send_otp_email(email: str, name: str, otp_code: str):
    """Send OTP email via EmailJS API (server-side)."""
    # Guard: warn early if any credential is missing / still placeholder
    missing = []
    for key, val in [
        ("EMAILJS_SERVICE_ID",  EMAILJS_SERVICE_ID),
        ("EMAILJS_TEMPLATE_ID", EMAILJS_TEMPLATE_ID),
        ("EMAILJS_PUBLIC_KEY",  EMAILJS_PUBLIC_KEY),
        ("EMAILJS_PRIVATE_KEY", EMAILJS_PRIVATE_KEY),
    ]:
        if not val or val.startswith("YOUR_"):
            missing.append(key)
    if missing:
        print(f"[EMAIL] SKIPPED – missing/placeholder credentials: {', '.join(missing)}")
        print(f"[EMAIL] Fill in the real values in your .env file and restart the server.")
        return False

    try:
        url = "https://api.emailjs.com/api/v1.0/email/send"

        payload = {
            "service_id": EMAILJS_SERVICE_ID,
            "template_id": EMAILJS_TEMPLATE_ID,
            "user_id": EMAILJS_PUBLIC_KEY,
            "accessToken": EMAILJS_PRIVATE_KEY,
            "template_params": {
                "to_email": email,
                "to_name": name,
                "otp_code": otp_code,
                "reply_to": email
            }
        }

        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)

        if response.status_code == 200:
            print(f"[EMAIL] OTP email sent successfully to {email}")
            return True
        else:
            # Log full response body so you can see the exact EmailJS error
            print(f"[EMAIL] Failed to send email - status: {response.status_code}")
            print(f"[EMAIL] EmailJS response body: {response.text}")
            return False
    except Exception as e:
        print(f"[EMAIL] Email service exception: {type(e).__name__}: {e}")
        return False


def verify_otp(email: str, otp_code: str):
    """Verify OTP code for registration and return temp user data if valid."""
    conn = get_db()
    c = conn.cursor()

    # Fetch all unverified OTPs for this email (to check hash)
    c.execute("""
        SELECT id, otp_code, temp_user_data, expires_at, purpose FROM otp_verification 
        WHERE email=? AND verified=0 AND purpose='registration'
        ORDER BY created_at DESC
    """, (email,))

    results = c.fetchall()

    if not results:
        conn.close()
        return None

    # Try to verify hash against each stored OTP
    for row_id, stored_hash, temp_user_data, expires_at, purpose in results:
        if verify_otp_hash(otp_code, stored_hash):
            # Check if OTP has expired
            if datetime.now() > datetime.fromisoformat(expires_at):
                conn.close()
                return None

            # Mark OTP as verified using row ID to avoid race conditions
            c.execute("""
                UPDATE otp_verification 
                SET verified=1 
                WHERE id=?
            """, (row_id,))

            conn.commit()
            conn.close()

            return temp_user_data

    conn.close()
    return None

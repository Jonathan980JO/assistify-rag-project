"""Pure OTP hashing/generation helpers for the login system.

Extracted verbatim from ``login_server.py`` during the Phase 1 refactor.
No database access, no FastAPI imports, no module-global state.
"""
import hashlib
import random
import string


def hash_otp(otp: str) -> str:
    """Hash OTP before storing in database"""
    return hashlib.sha256(otp.encode()).hexdigest()


def verify_otp_hash(otp: str, hashed: str) -> bool:
    """Verify OTP against hash"""
    return hash_otp(otp) == hashed


def generate_otp(length=6):
    """Generate a random OTP code."""
    return ''.join(random.choices(string.digits, k=length))

"""Pure input-validation helpers for the login system.

Extracted verbatim from ``login_server.py`` during the Phase 1 refactor.
No database access, no FastAPI imports, no module-global state.
"""


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength and length.
    Returns (is_valid, error_message)
    """
    # Development: relax password rules for easier testing
    try:
        from config import IS_PRODUCTION
    except Exception:
        IS_PRODUCTION = True

    if not IS_PRODUCTION:
        # In development allow shorter/simple passwords (do basic length>0 check)
        if len(password) == 0:
            return False, "Password cannot be empty"
        return True, ""

    # Check length (8-128 characters)
    if not (8 <= len(password) <= 128):
        return False, "Password must be between 8 and 128 characters"
    
    # Basic complexity checks
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
    
    if not (has_upper or has_lower):
        return False, "Password must contain letters"
    
    if not (has_digit or has_special):
        return False, "Password must contain numbers or special characters"
    
    return True, ""


def validate_email(email: str) -> bool:
    """Validate email format."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email)) and len(email) <= 254


def validate_username(username: str) -> tuple[bool, str]:
    """Validate username format.
    Returns (is_valid, error_message)
    """
    if not (3 <= len(username) <= 50):
        return False, "Username must be between 3 and 50 characters"
    
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, underscores, and hyphens"
    
    return True, ""


def sanitize_input(text: str, max_length: int = 500) -> str:
    """Sanitize user input by stripping and truncating."""
    if not text:
        return ""
    return text.strip()[:max_length]

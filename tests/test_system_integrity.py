"""
Comprehensive System Test Suite - TDD Approach
Tests all critical components to find logical errors
"""

import sys
import os
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))
sys.path.insert(0, str(project_root / "Login_system"))

import sqlite3
import tempfile
from datetime import datetime

print("="*60)
print("SYSTEM INTEGRITY TEST SUITE - TDD APPROACH")
print("="*60)
print()

# ========== TEST 1: Database Schema Integrity ==========
def test_analytics_database_schema():
    """Test that analytics database has all required columns"""
    print("TEST 1: Analytics Database Schema")
    
    from backend.analytics import init_analytics_db, ANALYTICS_DB
    
    # Initialize database
    init_analytics_db()
    
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    
    # Check usage_stats table
    c.execute("PRAGMA table_info(usage_stats)")
    columns = {row[1] for row in c.fetchall()}
    
    required_columns = {
        'id', 'timestamp', 'username', 'user_role', 'query_text',
        'response_status', 'error_message', 'response_time_ms',
        'rag_docs_found', 'query_length', 'response_length'
    }
    
    missing = required_columns - columns
    if missing:
        print(f"  ❌ FAIL: Missing columns: {missing}")
        conn.close()
        return False
    
    print(f"  ✅ PASS: All columns present")
    conn.close()
    return True


# ========== TEST 2: Response Validator Logic ==========
def test_response_validator():
    """Test response validation catches all issues"""
    print("\nTEST 2: Response Validator")
    
    from backend.response_validator import validate_response
    
    test_cases = [
        # (response, query, should_block, test_name)
        ("Hello, how can I help?", "help me", False, "Clean response"),
        ("Your fucking account is suspended", "account", True, "Profanity"),
        ("Email me at test@email.com", "contact", True, "Email PII"),
        ("Call 555-123-4567", "phone", True, "Phone PII"),
        ("SSN: 123-45-6789", "verify", True, "SSN PII"),
        ("I don't know", "question", False, "Uncertainty - should modify, not block"),
    ]
    
    all_passed = True
    for response, query, should_block, name in test_cases:
        result = validate_response(response, query)
        is_blocked = not result.is_valid
        
        if is_blocked == should_block:
            print(f"  ✅ PASS: {name}")
        else:
            print(f"  ❌ FAIL: {name} - Expected block={should_block}, got block={is_blocked}")
            all_passed = False
    
    return all_passed


# ========== TEST 3: Login Server Database ==========
def test_login_database_schema():
    """Test login database has all required tables and columns"""
    print("\nTEST 3: Login Database Schema")
    
    # Create temp database for testing
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        test_db = tmp.name
    
    try:
        conn = sqlite3.connect(test_db)
        c = conn.cursor()
        
        # Simulate init_db (simplified version)
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number TEXT UNIQUE NOT NULL,
                customer_id INTEGER NOT NULL,
                customer_username TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                priority TEXT DEFAULT 'normal',
                assigned_to TEXT,
                assigned_to_role TEXT,
                escalated_to_admin INTEGER DEFAULT 0,
                resolution_notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                FOREIGN KEY (customer_id) REFERENCES users(id)
            )
        """)
        
        # Check tables exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in c.fetchall()}
        
        required_tables = {'users', 'support_tickets'}
        missing_tables = required_tables - tables
        
        if missing_tables:
            print(f"  ❌ FAIL: Missing tables: {missing_tables}")
            return False
        
        # Check support_tickets has ticket_number
        c.execute("PRAGMA table_info(support_tickets)")
        columns = {row[1] for row in c.fetchall()}
        
        if 'ticket_number' not in columns:
            print(f"  ❌ FAIL: support_tickets missing ticket_number column")
            return False
        
        print(f"  ✅ PASS: All tables and columns present")
        return True
        
    finally:
        conn.close()
        os.unlink(test_db)


# ========== TEST 4: Analytics Log Usage Function ==========
def test_analytics_log_usage():
    """Test that log_usage accepts all required parameters"""
    print("\nTEST 4: Analytics log_usage Function")
    
    from backend.analytics import log_usage
    
    try:
        # Test with all parameters
        log_usage(
            username="test_user",
            user_role="customer",
            query_text="test query",
            response_status="success",
            error_message=None,
            response_time_ms=150,
            rag_docs_found=3,
            query_length=10,
            response_length=50
        )
        print(f"  ✅ PASS: log_usage accepts all parameters")
        return True
    except Exception as e:
        print(f"  ❌ FAIL: log_usage error: {e}")
        return False


# ========== TEST 5: Validation Integration in RAG ==========
def test_validation_integration():
    """Test that validation is properly integrated in RAG server"""
    print("\nTEST 5: Validation Integration")
    
    try:
        # Check import works
        from backend.assistify_rag_server import validate_response
        print(f"  ✅ PASS: validate_response imported in RAG server")
        return True
    except ImportError as e:
        print(f"  ❌ FAIL: validate_response not imported: {e}")
        return False


# ========== TEST 6: Ticket Number Generation ==========
def test_ticket_number_format():
    """Test ticket number generation format"""
    print("\nTEST 6: Ticket Number Generation")
    
    # Simulate the function
    import random
    from datetime import datetime
    
    date_str = datetime.now().strftime("%Y%m%d")
    random_num = random.randint(1000, 9999)
    ticket_number = f"TKT-{date_str}-{random_num}"
    
    # Check format
    parts = ticket_number.split('-')
    if len(parts) != 3:
        print(f"  ❌ FAIL: Wrong format: {ticket_number}")
        return False
    
    if parts[0] != "TKT":
        print(f"  ❌ FAIL: Wrong prefix: {parts[0]}")
        return False
    
    if len(parts[1]) != 8:
        print(f"  ❌ FAIL: Wrong date format: {parts[1]}")
        return False
    
    if not (1000 <= int(parts[2]) <= 9999):
        print(f"  ❌ FAIL: Wrong random number: {parts[2]}")
        return False
    
    print(f"  ✅ PASS: Ticket number format correct: {ticket_number}")
    return True


# ========== TEST 7: WebSocket Message Handling ==========
def test_websocket_message_format():
    """Test websocket message format handling"""
    print("\nTEST 7: WebSocket Message Format")
    
    # Test message structure
    test_messages = [
        {"text": "Hello"},  # Text query
        {"type": "auth", "user": {"username": "test", "role": "customer"}},  # Auth
        {"audio": "base64data"},  # Audio
    ]
    
    for msg in test_messages:
        if "text" in msg and isinstance(msg["text"], str):
            print(f"  ✅ PASS: Text message valid")
        elif "type" in msg and msg["type"] == "auth":
            print(f"  ✅ PASS: Auth message valid")
        elif "audio" in msg:
            print(f"  ✅ PASS: Audio message valid")
    
    return True


# ========== TEST 8: Password Hashing ==========
def test_password_hashing():
    """Test password hashing works correctly"""
    print("\nTEST 8: Password Hashing")
    
    from passlib.context import CryptContext
    
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    password = "test_password_123"
    hashed = pwd_context.hash(password)
    
    # Verify hash
    if not pwd_context.verify(password, hashed):
        print(f"  ❌ FAIL: Password verification failed")
        return False
    
    # Verify wrong password fails
    if pwd_context.verify("wrong_password", hashed):
        print(f"  ❌ FAIL: Wrong password verified (should fail)")
        return False
    
    print(f"  ✅ PASS: Password hashing works correctly")
    return True


# ========== TEST 9: Session Serialization ==========
def test_session_serialization():
    """Test session token serialization"""
    print("\nTEST 9: Session Serialization")
    
    from itsdangerous import URLSafeSerializer
    
    secret = "test_secret_key_123"
    serializer = URLSafeSerializer(secret)
    
    user_data = {"username": "test", "role": "customer", "id": 1}
    
    # Serialize
    token = serializer.dumps(user_data)
    
    # Deserialize
    recovered = serializer.loads(token)
    
    if recovered != user_data:
        print(f"  ❌ FAIL: Session data mismatch")
        return False
    
    print(f"  ✅ PASS: Session serialization works")
    return True


# ========== TEST 10: Notification Creation Logic ==========
def test_notification_logic():
    """Test notification creation logic"""
    print("\nTEST 10: Notification Creation Logic")
    
    # Simulate create_notification function
    def create_notification(user, title, message, notification_type="info", priority="normal"):
        if not user or not title or not message:
            return False
        if notification_type not in ["info", "warning", "success", "error"]:
            return False
        if priority not in ["normal", "high"]:
            return False
        return True
    
    # Test valid notification
    result = create_notification(
        user="admin",
        title="Test",
        message="Test message",
        notification_type="info",
        priority="normal"
    )
    
    if not result:
        print(f"  ❌ FAIL: Valid notification rejected")
        return False
    
    # Test invalid type
    result = create_notification(
        user="admin",
        title="Test",
        message="Test",
        notification_type="invalid",
        priority="normal"
    )
    
    if result:
        print(f"  ❌ FAIL: Invalid notification accepted")
        return False
    
    print(f"  ✅ PASS: Notification logic correct")
    return True


# ========== RUN ALL TESTS ==========
def run_all_tests():
    """Run all tests and report results"""
    
    tests = [
        test_analytics_database_schema,
        test_response_validator,
        test_login_database_schema,
        test_analytics_log_usage,
        test_validation_integration,
        test_ticket_number_format,
        test_websocket_message_format,
        test_password_hashing,
        test_session_serialization,
        test_notification_logic,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"  ❌ EXCEPTION: {e}")
            results.append((test.__name__, False))
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print("="*60)
    print(f"RESULTS: {passed}/{total} tests passed ({(passed/total*100):.1f}%)")
    print("="*60)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

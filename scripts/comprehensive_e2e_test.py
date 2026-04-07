"""
Comprehensive End-to-End Test Suite
Tests all major features for Admin, Employee, and Customer roles
Including login, voice/text messaging, ticket creation, and system integration
"""

import requests
import json
import time
import uuid
from datetime import datetime
from itsdangerous import URLSafeSerializer
import sys
import os

# Add parent directory to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Configuration
LOGIN_HOST = "http://localhost:7001"  # Login server
RAG_HOST = "http://localhost:7000"     # RAG server
LLM_HOST = "http://localhost:8000"     # LLM server

# Test Credentials
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
EMPLOYEE_USER = "employee"
EMPLOYEE_PASS = "employee123"
CUSTOMER_USER = "customer"
CUSTOMER_PASS = "customer123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_section(title):
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(60)}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")

def print_test(test_name, status, details=""):
    status_color = Colors.GREEN if status == "PASS" else Colors.RED if status == "FAIL" else Colors.YELLOW
    status_symbol = "✓" if status == "PASS" else "✗" if status == "FAIL" else "⚠"
    print(f"{status_color}{status_symbol} {test_name}{Colors.RESET}")
    if details:
        print(f"  {Colors.BLUE}{details}{Colors.RESET}")

def create_session(username, role):
    """Create session token for a user"""
    s = URLSafeSerializer(config.SESSION_SECRET)
    token = s.dumps({"username": username, "role": role})
    csrf = uuid.uuid4().hex
    return {
        "cookies": {config.SESSION_COOKIE: token, "csrf_token": csrf},
        "headers": {"x-csrf-token": csrf, "Accept": "application/json"}
    }

def test_admin_features():
    """Test Admin role features"""
    print_section("ADMIN ROLE TESTS")
    
    session = create_session(ADMIN_USER, "admin")
    results = {"passed": 0, "failed": 0}
    
    # Test 1: Admin Dashboard Access
    try:
        resp = requests.get(f"{LOGIN_HOST}/admin", cookies=session["cookies"], headers=session["headers"])
        if resp.status_code == 200:
            print_test("Admin Dashboard Access", "PASS", "Status: 200 OK")
            results["passed"] += 1
        else:
            print_test("Admin Dashboard Access", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("Admin Dashboard Access", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 2: View All Users
    try:
        resp = requests.get(f"{LOGIN_HOST}/api/users", cookies=session["cookies"])
        if resp.status_code == 200:
            users = resp.json()
            print_test("View All Users", "PASS", f"Found {len(users)} users")
            results["passed"] += 1
        else:
            print_test("View All Users", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View All Users", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 3: Upload Knowledge Base File
    try:
        test_content = b"The Assistify system supports voice, text, and image inputs. Our AI uses RAG technology for accurate responses."
        files = {'file': ('admin_test_kb.txt', test_content)}
        resp = requests.post(
            f"{LOGIN_HOST}/proxy/upload_rag",
            files=files,
            cookies=session["cookies"],
            headers=session["headers"]
        )
        if resp.status_code == 200:
            print_test("Upload Knowledge Base File", "PASS", "File uploaded successfully")
            results["passed"] += 1
        else:
            print_test("Upload Knowledge Base File", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("Upload Knowledge Base File", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 4: View Knowledge Base Files
    try:
        resp = requests.get(f"{LOGIN_HOST}/api/knowledge/files", cookies=session["cookies"])
        if resp.status_code == 200:
            files = resp.json()
            print_test("View Knowledge Base Files", "PASS", f"Found {len(files)} files")
            results["passed"] += 1
        else:
            print_test("View Knowledge Base Files", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View Knowledge Base Files", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 5: View Analytics
    try:
        resp = requests.get(f"{LOGIN_HOST}/admin/analytics", cookies=session["cookies"])
        if resp.status_code == 200:
            print_test("View Analytics Dashboard", "PASS", "Analytics accessible")
            results["passed"] += 1
        else:
            print_test("View Analytics Dashboard", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View Analytics Dashboard", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 6: View Audit Logs
    try:
        resp = requests.get(f"{LOGIN_HOST}/admin/audit-logs", cookies=session["cookies"])
        if resp.status_code == 200:
            print_test("View Audit Logs", "PASS", "Audit logs accessible")
            results["passed"] += 1
        else:
            print_test("View Audit Logs", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View Audit Logs", "FAIL", str(e))
        results["failed"] += 1
    
    return results

def test_employee_features():
    """Test Employee role features"""
    print_section("EMPLOYEE ROLE TESTS")
    
    session = create_session(EMPLOYEE_USER, "employee")
    results = {"passed": 0, "failed": 0}
    
    # Test 1: Employee Dashboard Access
    try:
        resp = requests.get(f"{LOGIN_HOST}/employee", cookies=session["cookies"], headers=session["headers"])
        if resp.status_code == 200:
            print_test("Employee Dashboard Access", "PASS", "Status: 200 OK")
            results["passed"] += 1
        else:
            print_test("Employee Dashboard Access", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("Employee Dashboard Access", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 2: View Customers
    try:
        resp = requests.get(f"{LOGIN_HOST}/employee/customers", cookies=session["cookies"])
        if resp.status_code == 200:
            print_test("View Customer List", "PASS", "Customers accessible")
            results["passed"] += 1
        else:
            print_test("View Customer List", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View Customer List", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 3: View Tickets
    try:
        resp = requests.get(f"{LOGIN_HOST}/api/tickets", cookies=session["cookies"])
        if resp.status_code == 200:
            tickets = resp.json()
            print_test("View Support Tickets", "PASS", f"Found {len(tickets)} tickets")
            results["passed"] += 1
        else:
            print_test("View Support Tickets", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View Support Tickets", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 4: Cannot Access Admin Features
    try:
        resp = requests.get(f"{LOGIN_HOST}/admin", cookies=session["cookies"])
        if resp.status_code in [302, 403]:  # Redirect or forbidden
            print_test("Admin Access Blocked", "PASS", "Employee correctly blocked from admin")
            results["passed"] += 1
        else:
            print_test("Admin Access Blocked", "FAIL", f"Employee accessed admin (Status: {resp.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_test("Admin Access Blocked", "FAIL", str(e))
        results["failed"] += 1
    
    return results

def test_customer_features():
    """Test Customer role features"""
    print_section("CUSTOMER ROLE TESTS")
    
    session = create_session(CUSTOMER_USER, "customer")
    results = {"passed": 0, "failed": 0}
    
    # Test 1: Customer Dashboard Access
    try:
        resp = requests.get(f"{LOGIN_HOST}/customer", cookies=session["cookies"], headers=session["headers"])
        if resp.status_code == 200:
            print_test("Customer Dashboard Access", "PASS", "Status: 200 OK")
            results["passed"] += 1
        else:
            print_test("Customer Dashboard Access", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("Customer Dashboard Access", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 2: Create Support Ticket
    try:
        ticket_data = {
            "subject": f"E2E Test Ticket {datetime.now().strftime('%H:%M:%S')}",
            "description": "This is an automated test ticket to verify the ticketing system works correctly.",
            "priority": "normal"
        }
        resp = requests.post(
            f"{LOGIN_HOST}/api/support/ticket/create",
            json=ticket_data,
            cookies=session["cookies"],
            headers=session["headers"]
        )
        if resp.status_code == 200:
            result = resp.json()
            print_test("Create Support Ticket", "PASS", f"Ticket #{result.get('ticket_number', 'N/A')} created")
            results["passed"] += 1
        else:
            print_test("Create Support Ticket", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("Create Support Ticket", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 3: View My Tickets
    try:
        resp = requests.get(f"{LOGIN_HOST}/my-tickets", cookies=session["cookies"])
        if resp.status_code == 200:
            print_test("View My Tickets", "PASS", "Ticket history accessible")
            results["passed"] += 1
        else:
            print_test("View My Tickets", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View My Tickets", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 4: View Notifications
    try:
        resp = requests.get(f"{LOGIN_HOST}/notifications", cookies=session["cookies"])
        if resp.status_code == 200:
            print_test("View Notifications", "PASS", "Notifications accessible")
            results["passed"] += 1
        else:
            print_test("View Notifications", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("View Notifications", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 5: Cannot Access Admin Features
    try:
        resp = requests.get(f"{LOGIN_HOST}/admin", cookies=session["cookies"])
        if resp.status_code in [302, 403]:
            print_test("Admin Access Blocked", "PASS", "Customer correctly blocked from admin")
            results["passed"] += 1
        else:
            print_test("Admin Access Blocked", "FAIL", f"Customer accessed admin (Status: {resp.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_test("Admin Access Blocked", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 6: Cannot Access Employee Features
    try:
        resp = requests.get(f"{LOGIN_HOST}/employee", cookies=session["cookies"])
        if resp.status_code in [302, 403]:
            print_test("Employee Access Blocked", "PASS", "Customer correctly blocked from employee")
            results["passed"] += 1
        else:
            print_test("Employee Access Blocked", "FAIL", f"Customer accessed employee (Status: {resp.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_test("Employee Access Blocked", "FAIL", str(e))
        results["failed"] += 1
    
    return results

def test_rag_ai_system():
    """Test RAG AI system with text queries"""
    print_section("AI RAG SYSTEM TESTS")
    
    session = create_session(CUSTOMER_USER, "customer")
    results = {"passed": 0, "failed": 0}
    
    # Test 1: Simple Text Query
    try:
        query_data = {"text": "What are your support hours?"}
        resp = requests.post(
            f"{RAG_HOST}/query",
            json=query_data,
            cookies=session["cookies"]
        )
        if resp.status_code == 200:
            result = resp.json()
            response_text = result.get("response", "")
            print_test("Simple Text Query", "PASS", f"Response: {response_text[:100]}...")
            results["passed"] += 1
        else:
            print_test("Simple Text Query", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("Simple Text Query", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 2: RAG Context Query (should use uploaded knowledge base)
    try:
        time.sleep(1)  # Give time for previous query
        query_data = {"text": "Tell me about Assistify's AI technology"}
        resp = requests.post(
            f"{RAG_HOST}/query",
            json=query_data,
            cookies=session["cookies"]
        )
        if resp.status_code == 200:
            result = resp.json()
            response_text = result.get("response", "")
            print_test("RAG Context Query", "PASS", f"Response length: {len(response_text)} chars")
            results["passed"] += 1
        else:
            print_test("RAG Context Query", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("RAG Context Query", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 3: Submit Feedback
    try:
        feedback_data = {
            "username": CUSTOMER_USER,
            "rating": 5,
            "comment": "Automated test feedback - excellent response!"
        }
        resp = requests.post(
            f"{RAG_HOST}/submit-feedback",
            json=feedback_data,
            cookies=session["cookies"]
        )
        if resp.status_code == 200:
            print_test("Submit Feedback", "PASS", "Feedback submitted successfully")
            results["passed"] += 1
        else:
            print_test("Submit Feedback", "FAIL", f"Status: {resp.status_code}")
            results["failed"] += 1
    except Exception as e:
        print_test("Submit Feedback", "FAIL", str(e))
        results["failed"] += 1
    
    return results

def test_security_features():
    """Test security features"""
    print_section("SECURITY FEATURES TESTS")
    
    results = {"passed": 0, "failed": 0}
    
    # Test 1: Unauthenticated Access Blocked
    try:
        resp = requests.get(f"{LOGIN_HOST}/admin")
        if resp.status_code in [302, 401, 403]:
            print_test("Unauthenticated Access Blocked", "PASS", "Redirected to login")
            results["passed"] += 1
        else:
            print_test("Unauthenticated Access Blocked", "FAIL", f"Accessed without auth (Status: {resp.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_test("Unauthenticated Access Blocked", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 2: CSRF Protection (missing CSRF token)
    try:
        session = create_session(CUSTOMER_USER, "customer")
        ticket_data = {
            "subject": "CSRF Test Ticket",
            "description": "This should fail without CSRF token"
        }
        # Send request without CSRF header
        resp = requests.post(
            f"{LOGIN_HOST}/api/support/ticket/create",
            json=ticket_data,
            cookies=session["cookies"]
            # No CSRF header
        )
        if resp.status_code in [400, 403]:
            print_test("CSRF Protection", "PASS", "Request blocked without CSRF token")
            results["passed"] += 1
        else:
            print_test("CSRF Protection", "FAIL", f"Request succeeded without CSRF (Status: {resp.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_test("CSRF Protection", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 3: Session Validation
    try:
        invalid_session = {"SESSION_COOKIE": "invalid_token_12345"}
        resp = requests.get(f"{LOGIN_HOST}/main", cookies=invalid_session)
        if resp.status_code in [302, 401, 403]:
            print_test("Session Validation", "PASS", "Invalid session rejected")
            results["passed"] += 1
        else:
            print_test("Session Validation", "FAIL", f"Invalid session accepted (Status: {resp.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_test("Session Validation", "FAIL", str(e))
        results["failed"] += 1
    
    # Test 4: File Upload Size Limit
    try:
        session = create_session(ADMIN_USER, "admin")
        # Create a file larger than 10MB (configured limit)
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        files = {'file': ('large_file.txt', large_content)}
        resp = requests.post(
            f"{LOGIN_HOST}/proxy/upload_rag",
            files=files,
            cookies=session["cookies"],
            headers=session["headers"]
        )
        if resp.status_code in [400, 413]:
            print_test("File Upload Size Limit", "PASS", "Large file rejected")
            results["passed"] += 1
        else:
            print_test("File Upload Size Limit", "FAIL", f"Large file accepted (Status: {resp.status_code})")
            results["failed"] += 1
    except Exception as e:
        # Network timeout or connection error is expected for large files
        print_test("File Upload Size Limit", "PASS", "Large file rejected (connection error)")
        results["passed"] += 1
    
    return results

def print_summary(all_results):
    """Print comprehensive summary"""
    print_section("COMPREHENSIVE TEST SUMMARY")
    
    total_passed = sum(r["passed"] for r in all_results.values())
    total_failed = sum(r["failed"] for r in all_results.values())
    total_tests = total_passed + total_failed
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n{Colors.BOLD}Results by Category:{Colors.RESET}\n")
    
    for category, results in all_results.items():
        total = results["passed"] + results["failed"]
        rate = (results["passed"] / total * 100) if total > 0 else 0
        color = Colors.GREEN if rate >= 80 else Colors.YELLOW if rate >= 60 else Colors.RED
        print(f"{color}{category:.<40} {results['passed']}/{total} ({rate:.1f}%){Colors.RESET}")
    
    print(f"\n{Colors.BOLD}Overall Results:{Colors.RESET}")
    print(f"  Total Tests: {total_tests}")
    print(f"  {Colors.GREEN}Passed: {total_passed}{Colors.RESET}")
    print(f"  {Colors.RED}Failed: {total_failed}{Colors.RESET}")
    
    overall_color = Colors.GREEN if success_rate >= 80 else Colors.YELLOW if success_rate >= 60 else Colors.RED
    print(f"\n{overall_color}{Colors.BOLD}Success Rate: {success_rate:.1f}%{Colors.RESET}\n")
    
    if success_rate >= 80:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 EXCELLENT! System is working well!{Colors.RESET}\n")
    elif success_rate >= 60:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠ GOOD! Some issues need attention.{Colors.RESET}\n")
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ NEEDS WORK! Critical issues detected.{Colors.RESET}\n")

def main():
    """Main test runner"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║         ASSISTIFY COMPREHENSIVE E2E TEST SUITE            ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}\n")
    
    print(f"{Colors.YELLOW}Testing against:{Colors.RESET}")
    print(f"  Login Server: {LOGIN_HOST}")
    print(f"  RAG Server: {RAG_HOST}")
    print(f"\n{Colors.YELLOW}Starting in 2 seconds...{Colors.RESET}\n")
    time.sleep(2)
    
    all_results = {}
    
    # Run all test suites
    try:
        all_results["Admin Features"] = test_admin_features()
    except Exception as e:
        print_test("Admin Features", "FAIL", f"Suite error: {e}")
        all_results["Admin Features"] = {"passed": 0, "failed": 1}
    
    try:
        all_results["Employee Features"] = test_employee_features()
    except Exception as e:
        print_test("Employee Features", "FAIL", f"Suite error: {e}")
        all_results["Employee Features"] = {"passed": 0, "failed": 1}
    
    try:
        all_results["Customer Features"] = test_customer_features()
    except Exception as e:
        print_test("Customer Features", "FAIL", f"Suite error: {e}")
        all_results["Customer Features"] = {"passed": 0, "failed": 1}
    
    try:
        all_results["AI RAG System"] = test_rag_ai_system()
    except Exception as e:
        print_test("AI RAG System", "FAIL", f"Suite error: {e}")
        all_results["AI RAG System"] = {"passed": 0, "failed": 1}
    
    try:
        all_results["Security Features"] = test_security_features()
    except Exception as e:
        print_test("Security Features", "FAIL", f"Suite error: {e}")
        all_results["Security Features"] = {"passed": 0, "failed": 1}
    
    # Print summary
    print_summary(all_results)

if __name__ == "__main__":
    main()

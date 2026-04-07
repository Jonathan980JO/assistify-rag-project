"""
Response Validation Module - Basic Level
Validates AI responses before sending to users
"""

import re
import logging

logger = logging.getLogger("Assistify.Validator")

# ========== CONFIGURATION ==========

# Profanity and sensitive terms blocklist
BLOCKED_WORDS = [
    # Profanity (common variants - including derivatives)
    'fuck', 'fucking', 'fucked', 'shit', 'shitty', 'bitch', 'bitching',
    'ass', 'asshole', 'damn', 'damned', 'hell', 'crap', 'crappy',
    'bastard', 'dick', 'piss', 'pissed', 'cock', 'pussy', 'whore', 'slut',
    
    # Discriminatory terms
    'nigger', 'faggot', 'retard', 'retarded', 'chink', 'kike', 'spic',
    
    # Sensitive business terms that AI should never promise
    'refund guaranteed', 'free money', 'lawsuit', 'sue us',
    'illegal', 'scam', 'fraud',
]

# PII patterns
PII_PATTERNS = {
    'ssn': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    'credit_card': re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
}

# Company contact information patterns (these are ALLOWED in responses)
COMPANY_CONTACT_PATTERNS = [
    re.compile(r'\bhelp@assistify\.com\b', re.IGNORECASE),
    re.compile(r'\bsupport@assistify\.com\b', re.IGNORECASE),
    re.compile(r'\binfo@assistify\.com\b', re.IGNORECASE),
    re.compile(r'\bcontact@assistify\.com\b', re.IGNORECASE),
    re.compile(r'\bassistify\.com\b', re.IGNORECASE),
    # Add phone patterns if you have official support numbers
    re.compile(r'\b1[-.]?800[-.]?\d{3}[-.]?\d{4}\b'),  # 1-800 numbers are public
]

# Uncertainty indicators
UNCERTAINTY_PHRASES = [
    "i don't know",
    "i'm not sure",
    "i cannot",
    "i can't",
    "unable to",
    "not certain",
    "unclear",
    "unsure",
]


# ========== VALIDATION FUNCTIONS ==========

def contains_profanity(text: str) -> tuple[bool, list]:
    """Check if text contains blocked words."""
    text_lower = text.lower()
    found_words = []
    
    for word in BLOCKED_WORDS:
        # Use word boundaries to avoid false positives
        pattern = r'\b' + re.escape(word) + r'\b'
        if re.search(pattern, text_lower):
            found_words.append(word)
    
    return len(found_words) > 0, found_words


def contains_pii(text: str) -> tuple[bool, list]:
    """
    Check if text contains personally identifiable information.
    NOTE: Company contact info (official support emails/phones) is ALLOWED.
    Only blocks sensitive personal data like SSN, credit cards, etc.
    """
    found_pii = []
    
    # First check if text contains company contact information - if so, it's allowed
    for company_pattern in COMPANY_CONTACT_PATTERNS:
        if company_pattern.search(text):
            # This is official company contact info, allow it
            return False, []
    
    # Check for actual sensitive PII (SSN, credit cards, etc.)
    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            found_pii.append(pii_type)
    
    return len(found_pii) > 0, found_pii


def is_uncertain(text: str) -> bool:
    """Check if response indicates uncertainty."""
    text_lower = text.lower()
    
    for phrase in UNCERTAINTY_PHRASES:
        if phrase in text_lower:
            return True
    
    return False


def check_relevance(response: str, user_query: str) -> bool:
    """
    Basic relevance check: does response share keywords with query?
    Returns True if relevant, False if completely off-topic.
    """
    # Extract meaningful words (3+ chars) from query
    query_words = set(
        word.lower() 
        for word in re.findall(r'\b\w{3,}\b', user_query)
        if word.lower() not in {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 'did', 'let', 'put', 'say', 'she', 'too', 'use'}
    )
    
    # Extract words from response
    response_words = set(
        word.lower() 
        for word in re.findall(r'\b\w{3,}\b', response)
    )
    
    # Check overlap
    overlap = query_words & response_words
    
    # If there's at least 1 shared meaningful word, consider it relevant
    # Or if response is very short (likely acknowledgment)
    return len(overlap) > 0 or len(response) < 50


def add_uncertainty_disclaimer(text: str) -> str:
    """Add disclaimer to uncertain responses."""
    disclaimer = "\n\n*Note: I'm not completely certain about this. You may want to verify with our support team.*"
    
    # Don't add if already has a disclaimer
    if "not completely certain" in text.lower() or "verify" in text.lower():
        return text
    
    return text + disclaimer


# ========== MAIN VALIDATION FUNCTION ==========

class ValidationResult:
    """Result of response validation."""
    def __init__(self):
        self.is_valid = True
        self.modified_response = None
        self.issues = []
        self.severity = "none"  # none, minor, major, critical
        
    def add_issue(self, severity: str, message: str):
        """Add a validation issue."""
        self.issues.append({"severity": severity, "message": message})
        
        # Update overall severity
        severity_levels = {"none": 0, "minor": 1, "major": 2, "critical": 3}
        if severity_levels.get(severity, 0) > severity_levels.get(self.severity, 0):
            self.severity = severity


def validate_response(response: str, user_query: str = "", rag_context: list = None) -> ValidationResult:
    """
    Validate AI response before sending to user.
    
    Args:
        response: The AI-generated response text
        user_query: The original user question (for relevance check)
        rag_context: List of RAG documents used (optional)
    
    Returns:
        ValidationResult object with validation status and modified response
    """
    result = ValidationResult()
    
    # Handle None/empty inputs
    if response is None:
        response = ""
    if user_query is None:
        user_query = ""
    
    # If response is empty, return invalid
    if not response.strip():
        result.is_valid = False
        result.add_issue("critical", "Empty response")
        result.modified_response = "I apologize, but I couldn't generate a proper response. How can I help you?"
        return result
    
    modified_response = response
    
    # 1. Profanity Check (CRITICAL)
    has_profanity, bad_words = contains_profanity(response)
    if has_profanity:
        result.is_valid = False
        result.add_issue("critical", f"Contains profanity: {bad_words}")
        logger.warning(f"BLOCKED: Response contains profanity: {bad_words}")
        modified_response = "I apologize, but I'm unable to provide that response. How else can I help you?"
        result.modified_response = modified_response
        return result  # Return immediately on critical failure
    
    # 2. PII Check (CRITICAL)
    has_pii, pii_types = contains_pii(response)
    if has_pii:
        result.is_valid = False
        result.add_issue("critical", f"Contains PII: {pii_types}")
        logger.warning(f"BLOCKED: Response contains PII: {pii_types}")
        modified_response = "I apologize, but that response contains sensitive information. Let me help you differently."
        result.modified_response = modified_response
        return result  # Return immediately on critical failure
    
    # 3. Relevance Check (MAJOR)
    if user_query:
        is_relevant = check_relevance(response, user_query)
        if not is_relevant:
            result.add_issue("major", "Response may be off-topic")
            logger.warning(f"WARNING: Response may not be relevant to query: '{user_query[:50]}'")
            # Don't block, but log for analytics
    
    # 4. Uncertainty Check (MINOR - auto-fix)
    if is_uncertain(response):
        result.add_issue("minor", "Response indicates uncertainty")
        logger.info("INFO: Response shows uncertainty, adding disclaimer")
        modified_response = add_uncertainty_disclaimer(response)
    
    # Set modified response if any changes were made
    if modified_response != response:
        result.modified_response = modified_response
    
    logger.info(f"Validation result: {result.severity} - {len(result.issues)} issue(s)")
    return result


def get_safe_fallback_response() -> str:
    """Return a safe generic response when validation fails."""
    return "I apologize, but I'm having trouble formulating an appropriate response. Could you please rephrase your question, or would you like to speak with a human support agent?"


# ========== TESTING ==========

if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("Hello, how can I help you today?", "greeting", True),
        ("Your account has been fucking suspended!", "profanity test", False),
        ("Please contact me at john@email.com", "PII test", False),
        ("I don't know the answer to that question.", "uncertainty test", True),
        ("The weather is nice today.", "irrelevant to tech support", True),
        ("Your SSN is 123-45-6789", "SSN leak", False),
    ]
    
    print("Running validation tests...\n")
    for response, test_name, should_pass in test_cases:
        result = validate_response(response, "help me with my account")
        status = "✓ PASS" if result.is_valid == should_pass else "✗ FAIL"
        print(f"{status} - {test_name}")
        print(f"  Original: {response[:60]}")
        if result.modified_response:
            print(f"  Modified: {result.modified_response[:60]}")
        print(f"  Severity: {result.severity}")
        if result.issues:
            for issue in result.issues:
                print(f"    - {issue['severity']}: {issue['message']}")
        print()

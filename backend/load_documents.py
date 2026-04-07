# load_documents.py - Load your support documents into the knowledge base
from backend.knowledge_base import add_document, clear_knowledge_base, get_all_documents

# Sample support documents for your AI support system
SUPPORT_DOCUMENTS = [
    {
        "id": "return_policy",
        "text": "Our return policy allows customers to return products within 30 days of purchase with a valid receipt. Items must be in original condition with tags attached. Refunds are processed within 5-7 business days after we receive the returned item. For online purchases, customers are responsible for return shipping costs unless the item is defective.",
        "metadata": {"category": "returns", "type": "policy"}
    },
    {
        "id": "password_reset",
        "text": "To reset your password, follow these steps: 1) Go to the login page and click 'Forgot Password' 2) Enter your registered email address 3) Check your email inbox for a password reset link 4) Click the link (valid for 24 hours) 5) Enter and confirm your new password 6) Log in with your new credentials. If you don't receive the email within 10 minutes, check your spam folder.",
        "metadata": {"category": "account", "type": "how-to"}
    },
    {
        "id": "shipping_info",
        "text": "We offer free standard shipping on orders over $50. Standard shipping takes 3-5 business days. Express shipping is available for $15 and takes 1-2 business days. International shipping rates vary by location and typically take 7-14 business days. All orders are shipped Monday through Friday, excluding holidays. You will receive a tracking number via email once your order ships.",
        "metadata": {"category": "shipping", "type": "policy"}
    },
    {
        "id": "contact_hours",
        "text": "Our customer support team is available Monday through Friday from 9:00 AM to 6:00 PM EST. We are closed on weekends and major holidays. For urgent issues outside business hours, please email support@assistify.com and we will respond within 24 hours. Live chat support is available during business hours on our website.",
        "metadata": {"category": "contact", "type": "info"}
    },
    {
        "id": "warranty_info",
        "text": "All products come with a 1-year manufacturer's warranty covering defects in materials and workmanship. The warranty does not cover normal wear and tear, accidental damage, or misuse. To file a warranty claim, contact our support team with your order number and description of the issue. Extended warranty options are available at checkout for 2 or 3 year coverage.",
        "metadata": {"category": "warranty", "type": "policy"}
    },
    {
        "id": "payment_methods",
        "text": "We accept all major credit cards (Visa, MasterCard, American Express, Discover), PayPal, Apple Pay, and Google Pay. For large orders over $1000, we also accept bank transfers and purchase orders from verified business accounts. All transactions are secured with 256-bit SSL encryption. We do not store credit card information on our servers.",
        "metadata": {"category": "payment", "type": "info"}
    },
    {
        "id": "account_creation",
        "text": "To create an account, click 'Sign Up' on the homepage. Enter your name, email address, and create a secure password (minimum 8 characters with at least one number and one special character). Verify your email by clicking the link sent to your inbox. Once verified, you can track orders, save shipping addresses, and access your purchase history.",
        "metadata": {"category": "account", "type": "how-to"}
    },
    {
        "id": "order_tracking",
        "text": "To track your order, log into your account and go to 'My Orders'. Click on the order number to see detailed tracking information. You will also receive email updates when your order ships and when it's out for delivery. If tracking shows no movement for more than 3 business days, please contact our support team.",
        "metadata": {"category": "orders", "type": "how-to"}
    },
    {
        "id": "cancellation_policy",
        "text": "Orders can be cancelled within 2 hours of placement for a full refund. After 2 hours, if the order hasn't shipped yet, cancellation may be possible - contact support immediately. Once an order has shipped, it cannot be cancelled but can be returned following our return policy. Cancellation refunds are processed within 3-5 business days.",
        "metadata": {"category": "orders", "type": "policy"}
    },
    {
        "id": "technical_support",
        "text": "For technical issues with our products, first check our troubleshooting guide at support.assistify.com. Common issues can often be resolved by restarting the device, checking connections, or updating firmware. If problems persist, contact our technical support team with your product model number and a description of the issue. Remote support sessions are available for complex problems.",
        "metadata": {"category": "technical", "type": "info"}
    }
]

def load_all_documents(clear_first=False):
    """Load all support documents into the knowledge base"""
    
    if clear_first:
        print("Clearing existing knowledge base...")
        clear_knowledge_base()
    
    print(f"\nLoading {len(SUPPORT_DOCUMENTS)} documents...")
    
    success_count = 0
    for doc in SUPPORT_DOCUMENTS:
        if add_document(doc["id"], doc["text"], doc["metadata"]):
            success_count += 1
    
    print(f"\n✓ Successfully loaded {success_count}/{len(SUPPORT_DOCUMENTS)} documents")
    
    # Verify
    all_docs = get_all_documents()
    print(f"✓ Total documents in knowledge base: {len(all_docs)}")

def test_search():
    """Test searching the knowledge base"""
    from backend.knowledge_base import search_documents
    
    print("\n" + "="*60)
    print("Testing Search Functionality")
    print("="*60)
    
    test_queries = [
        "How do I reset my password?",
        "What is your return policy?",
        "How long does shipping take?",
        "What are your support hours?",
        "Can I cancel my order?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        results = search_documents(query, top_k=2)
        for i, doc in enumerate(results, 1):
            print(f"  {i}. {doc[:100]}...")

if __name__ == "__main__":
    print("="*60)
    print("Assistify Knowledge Base Loader")
    print("="*60)
    
    # Load documents (set clear_first=True to replace existing)
    load_all_documents(clear_first=True)
    
    # Test searches
    test_search()
    
    print("\n✓ Knowledge base ready!")

"""Debug script to test 400 Bad Request issue"""
import sys
sys.path.insert(0, r'c:\Users\Jonathan\Desktop\AAST\Graduation Project')

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from config import ALLOWED_HOSTS, ENFORCE_HTTPS

print("=" * 60)
print("CONFIGURATION TEST")
print("=" * 60)
print(f"ALLOWED_HOSTS: {ALLOWED_HOSTS}")
print(f"Type: {type(ALLOWED_HOSTS)}")
print(f"ENFORCE_HTTPS: {ENFORCE_HTTPS}")
print("=" * 60)

# Create minimal app with security middleware
app = FastAPI()

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses"""
    print(f"[MIDDLEWARE] Processing request: {request.url.path}")
    print(f"[MIDDLEWARE] Host header: {request.headers.get('host')}")
    response = await call_next(request)
    
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.emailjs.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.emailjs.com ws: wss:; "
        "font-src 'self'; "
        "frame-ancestors 'none';"
    )
    
    # HTTPS enforcement in production
    if ENFORCE_HTTPS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    print(f"[MIDDLEWARE] Response status: {response.status_code}")
    return response

# CORS (adjust for your needs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:7001", "http://127.0.0.1:7001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

@app.get("/")
def root_redirect(request: Request):
    """Redirect root to login page."""
    print("[ENDPOINT] Root handler called")
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login")
def login_page(request: Request):
    print("[ENDPOINT] Login handler called")
    return {"message": "Login page"}

if __name__ == "__main__":
    import uvicorn
    print("\nStarting test server on http://127.0.0.1:9999")
    print("Test with: curl -v http://127.0.0.1:9999/")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=9999, log_level="debug")

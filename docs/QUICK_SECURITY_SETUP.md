# Quick Security Setup Guide

## For Production Deployment

### Step 1: Generate Session Secret
```powershell
# Generate a secure 64-byte session secret
python -c "import secrets; print(secrets.token_hex(64))"
```

### Step 2: Create `.env` File
```powershell
# Copy the example file
Copy-Item .env.example .env
```

### Step 3: Edit `.env` File
Open `.env` and update:

1. **SESSION_SECRET**: Paste the generated secret from Step 1
2. **GOOGLE_CLIENT_ID**: Your Google OAuth client ID
3. **GOOGLE_CLIENT_SECRET**: Your Google OAuth client secret
4. **EMAILJS_PUBLIC_KEY**: Your EmailJS public key
5. **EMAILJS_PRIVATE_KEY**: Your EmailJS private key
6. **EMAILJS_SERVICE_ID**: Your EmailJS service ID
7. **EMAILJS_TEMPLATE_ID**: Your EmailJS template ID
8. **ENVIRONMENT**: Set to `production`
9. **ENFORCE_HTTPS**: Set to `true`

### Step 4: Verify Configuration
```powershell
# Test that the application starts correctly
$env:ENVIRONMENT="production"
python Login_system/login_server.py
```

**Expected Result**: 
- ✅ Application starts successfully
- ❌ If it exits with an error, check your `.env` file

### Step 5: Security Checklist

Before going live, verify:

- [ ] `.env` file exists and has all required variables
- [ ] `SESSION_SECRET` is at least 64 bytes (128 hex characters)
- [ ] `ENVIRONMENT=production` in `.env`
- [ ] `ENFORCE_HTTPS=true` in `.env`
- [ ] `.env` is NOT committed to version control (check `.gitignore`)
- [ ] Google OAuth credentials are correct
- [ ] EmailJS credentials are correct
- [ ] Test login works
- [ ] Test registration with OTP works
- [ ] Test password reset works

---

## For Development

### Step 1: Set Development Environment
```powershell
# Create .env file
Copy-Item .env.example .env
```

### Step 2: Edit `.env` for Development
```bash
ENVIRONMENT=development
# Leave other values as placeholders - they'll use fallbacks with warnings
```

### Step 3: Start Services
```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Start login server
python Login_system/login_server.py

# Start RAG server (in another terminal)
uvicorn backend.assistify_rag_server:app --reload --port 7000
```

---

## Getting OAuth Credentials

### Google OAuth
See `GOOGLE_OAUTH_SETUP.md` for step-by-step instructions.

**Quick Steps**:
1. Go to https://console.cloud.google.com/apis/credentials
2. Create new OAuth 2.0 Client ID
3. Set authorized redirect URI: `http://localhost:5000/auth/google`
4. Copy Client ID and Client Secret to `.env`

### EmailJS
See `EMAILJS_SETUP.md` for step-by-step instructions.

**Quick Steps**:
1. Sign up at https://www.emailjs.com/
2. Create email service
3. Create email template with variables: `to_email`, `to_name`, `otp_code`
4. Get Public Key, Private Key, Service ID, Template ID
5. Add all to `.env`

---

## Security Features Enabled

✅ **Environment Variable Enforcement**: Production won't start without secrets  
✅ **OTP Hashing**: OTPs hashed with SHA-256 before storage  
✅ **Rate Limiting**: 5 login attempts/min, 3 registration/OTP attempts/min  
✅ **Secure Cookies**: HttpOnly, Secure (HTTPS), SameSite=strict, 24h expiry  
✅ **Security Headers**: CSP, HSTS, X-Frame-Options, etc.  
✅ **Password Hashing**: Bcrypt with 12 rounds  
✅ **Role-Based Access**: Admin, Employee, Customer with strict permissions  
✅ **Audit Logging**: All sensitive actions logged with performer tracking  

---

## Troubleshooting

### Application exits immediately in production
**Cause**: Missing or invalid environment variables  
**Fix**: Check `.env` file has all required variables set

### "SESSION_SECRET must be at least 64 bytes"
**Cause**: Session secret is too short  
**Fix**: Generate new secret with `python -c "import secrets; print(secrets.token_hex(64))"`

### OTP emails not sending
**Cause**: Invalid EmailJS credentials  
**Fix**: Verify `EMAILJS_*` variables in `.env` match your EmailJS account

### "Too many login attempts"
**Cause**: Rate limiting triggered (5 attempts/minute)  
**Fix**: Wait 60 seconds and try again

### Google Sign-In not working
**Cause**: Invalid Google OAuth credentials  
**Fix**: Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`

---

## Need Help?

- **Security Implementation**: See `SECURITY_IMPLEMENTATION.md`
- **Google OAuth Setup**: See `GOOGLE_OAUTH_SETUP.md`
- **EmailJS Setup**: See `EMAILJS_SETUP.md`
- **Full Documentation**: See `README.md`

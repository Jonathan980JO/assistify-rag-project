# Google OAuth Setup Guide

## 🔐 Setting Up Google OAuth for Assistify

This guide will help you configure Google OAuth authentication for customer sign-ins.

---

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **"Create Project"** or select an existing project
3. Give your project a name (e.g., "Assistify")
4. Click **"Create"**

---

## Step 2: Enable Google+ API

1. In your Google Cloud Project, go to **APIs & Services** → **Library**
2. Search for **"Google+ API"** (or "Google Identity")
3. Click **"Enable"**

---

## Step 3: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. If prompted, configure the **OAuth consent screen** first:
   - **User Type**: Choose "External" (for testing with any Google account)
   - **App name**: Assistify
   - **User support email**: Your email
   - **Developer contact**: Your email
   - **Scopes**: Add `openid`, `email`, `profile`
   - **Test users**: Add your Google account email (for testing)
   - Click **"Save and Continue"**

4. After configuring consent screen, create OAuth client ID:
   - **Application type**: Web application
   - **Name**: Assistify Web Client
   - **Authorized JavaScript origins**:
     - `http://localhost:7001`
     - `http://127.0.0.1:7001`
   - **Authorized redirect URIs**:
     - `http://localhost:7001/auth/google/callback`
     - `http://127.0.0.1:7001/auth/google/callback`
   - Click **"Create"**

5. **Copy your credentials**:
   - **Client ID**: Something like `123456789-abc...xyz.apps.googleusercontent.com`
   - **Client Secret**: Something like `GOCSPX-abc...xyz`

---

## Step 4: Configure Environment Variables

You have two options to set your Google OAuth credentials:

### Option A: Environment Variables (Recommended for Production)

Create a `.env` file in the project root:

```bash
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:7001/auth/google/callback
```

### Option B: Update config.py Directly (For Testing)

Edit `config.py` and replace the placeholder values:

```python
# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_ACTUAL_CLIENT_ID_HERE")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_ACTUAL_SECRET_HERE")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:7001/auth/google/callback")
```

---

## Step 5: Install Required Packages

Make sure you have the latest dependencies installed:

```powershell
pip install authlib httpx
```

Or install from requirements.txt:

```powershell
pip install -r requirements.txt
```

---

## Step 6: Test the Integration

1. **Start the server**:
   ```powershell
   python project_start_server.py --enforce-gpu --n-gpu-layers 40
   ```

2. **Navigate to the login page**:
   - Open: `http://localhost:7001/`

3. **Click "Continue with Google"**:
   - You should be redirected to Google's sign-in page
   - Sign in with your Google account
   - Grant permissions when prompted
   - You'll be redirected back to Assistify as a **customer** user

---

## How It Works

### Customer Sign-In Flow:

1. **User clicks "Continue with Google"**
2. **Redirected to Google** for authentication
3. **User grants permissions** (email, profile)
4. **Google redirects back** to `/auth/google/callback`
5. **System checks** if Google account exists:
   - **If exists**: Log user in
   - **If new**: Create new customer account automatically
6. **User is logged in** and redirected to customer dashboard (`/main`)

### User Data Collected:

- **Google ID**: Unique identifier from Google
- **Email**: User's Google email address
- **Name**: User's Google display name
- **Profile Picture**: User's Google profile picture URL
- **Role**: Automatically set to `customer`
- **Auth Provider**: Set to `google`

### Database Schema Changes:

New columns added to `users` table:
- `google_id` - Unique Google user identifier
- `email` - User's email address
- `profile_picture` - URL to profile picture
- `auth_provider` - Either 'local' or 'google'

---

## Security Features

✅ **Automatic Customer Role**: Google OAuth users are always created as customers
✅ **Admin/Employee Protection**: Only traditional login works for admin/employee roles
✅ **Email Verification**: Google handles email verification
✅ **Secure Token Exchange**: OAuth 2.0 standard flow
✅ **Session Management**: Same secure session system as traditional login
✅ **CSRF Protection**: CSRF tokens still generated for API calls

---

## Troubleshooting

### Error: "google_auth_failed"

**Possible causes**:
- Invalid Client ID or Client Secret
- Redirect URI mismatch (check Google Console)
- OAuth consent screen not configured
- User denied permissions

**Solution**:
1. Verify credentials in `config.py`
2. Check redirect URIs match exactly
3. Ensure OAuth consent screen is published
4. Check browser console for errors

### Error: "redirect_uri_mismatch"

**Solution**:
- Go to Google Cloud Console → Credentials
- Edit your OAuth client
- Add the exact redirect URI: `http://localhost:7001/auth/google/callback`

### Google Sign-In Button Not Working

**Solution**:
1. Check server logs for errors
2. Verify `authlib` and `httpx` are installed
3. Restart the server
4. Clear browser cache

---

## Production Deployment

When deploying to production:

1. **Update Redirect URIs** in Google Cloud Console:
   - Add your production domain (e.g., `https://yourdomain.com/auth/google/callback`)

2. **Update Environment Variables**:
   ```bash
   GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/google/callback
   ```

3. **OAuth Consent Screen**:
   - Switch from "Testing" to "In Production"
   - Complete verification process if needed

4. **Use HTTPS**: Google OAuth requires HTTPS in production

---

## Features

### ✅ What Works Now:

- **Google Sign-In button** on login page
- **Automatic customer account creation**
- **Email-based username** (e.g., `johnsmith` from `johnsmith@gmail.com`)
- **Profile picture storage** (can be used in future UI enhancements)
- **Seamless integration** with existing authentication system
- **Role-based access control** maintained

### 🔮 Future Enhancements:

- Display profile picture in dashboard
- Email notifications for new sign-ups
- Social profile integration
- Account linking (Google + traditional password)
- Additional OAuth providers (Microsoft, GitHub, etc.)

---

## Testing Checklist

- [ ] Install authlib and httpx packages
- [ ] Create Google Cloud Project
- [ ] Enable Google+ API
- [ ] Configure OAuth consent screen
- [ ] Create OAuth 2.0 credentials
- [ ] Copy Client ID and Secret to config.py
- [ ] Start server and navigate to login page
- [ ] Click "Continue with Google"
- [ ] Successfully sign in with Google account
- [ ] Verify user created in database as customer
- [ ] Check session works (can access /main)
- [ ] Test logout and re-login
- [ ] Verify admin/employee still use traditional login

---

## Support

If you encounter any issues:

1. Check the server console for detailed error messages
2. Verify all credentials are correctly configured
3. Ensure Google Cloud project quotas are not exceeded
4. Review Google OAuth documentation: https://developers.google.com/identity/protocols/oauth2

---

**Status**: ✅ Google OAuth is now integrated and ready to use once you configure the credentials!

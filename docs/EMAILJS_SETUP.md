# EmailJS Setup Guide for Assistify

## 📧 Free Email Service (No Domain Verification Required!)

EmailJS allows you to send emails directly from the browser without a backend email server.

---

## Step 1: Create EmailJS Account

1. Go to [EmailJS.com](https://www.emailjs.com/)
2. Click **"Sign Up"** (top right)
3. Create account with Google or email
4. Confirm your email address

---

## Step 2: Add Email Service

1. In EmailJS dashboard, click **"Email Services"**
2. Click **"Add New Service"**
3. Select your email provider:
   - **Gmail** (recommended for testing)
   - **Outlook**
   - **Yahoo**
   - Or any other SMTP service
4. Click **"Connect Account"** and authorize
5. Copy your **Service ID** (e.g., `service_abc123`)

---

## Step 3: Create Email Template

1. In EmailJS dashboard, click **"Email Templates"**
2. Click **"Create New Template"**
3. Set **Template Name**: `Assistify OTP Verification`
4. Paste this HTML template:

```html
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 600px;
            margin: 40px auto;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .header {
            background: linear-gradient(135deg, #10a37f 0%, #0d8658 100%);
            padding: 30px;
            text-align: center;
            color: white;
        }
        .header h1 {
            margin: 0;
            font-size: 28px;
        }
        .content {
            padding: 40px 30px;
        }
        .otp-box {
            background: #f8f9fa;
            border: 2px dashed #10a37f;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            margin: 30px 0;
        }
        .otp-code {
            font-size: 36px;
            font-weight: bold;
            color: #10a37f;
            letter-spacing: 8px;
            font-family: 'Courier New', monospace;
        }
        .info {
            color: #666;
            font-size: 14px;
            line-height: 1.6;
        }
        .footer {
            background: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            color: #999;
            font-size: 12px;
        }
        .warning {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin: 20px 0;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔐 Assistify</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">Email Verification</p>
        </div>
        <div class="content">
            <h2 style="color: #333; margin-top: 0;">Hello {{to_name}}!</h2>
            <p class="info">
                Thank you for signing up with Assistify. To complete your registration, 
                please use the verification code below:
            </p>
            <div class="otp-box">
                <div style="color: #666; font-size: 12px; margin-bottom: 10px;">YOUR VERIFICATION CODE</div>
                <div class="otp-code">{{otp_code}}</div>
            </div>
            <p class="info">
                This code will expire in <strong>10 minutes</strong>. If you didn't request this code, 
                please ignore this email.
            </p>
            <div class="warning">
                ⚠️ <strong>Security Notice:</strong> Never share this code with anyone. 
                Assistify will never ask for your verification code.
            </div>
        </div>
        <div class="footer">
            <p>This is an automated message from Assistify Help Desk System</p>
            <p>© 2025 Assistify. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
```

5. Set **Subject**: `Verify Your Assistify Account - Code: {{otp_code}}`
6. Click **"Save"**
7. Copy your **Template ID** (e.g., `template_xyz789`)

---

## Step 4: Get Your Public Key

1. In EmailJS dashboard, click **"Account"** → **"General"**
2. Find **"Public Key"** section
3. Copy your **Public Key** (e.g., `pk-aBcDeFg123456`)

---

## Step 5: Configure Assistify

Edit `verify_otp.html` and replace the placeholders:

1. Open: `Login_system/templates/verify_otp.html`
2. Find line 7:
   ```javascript
   publicKey: "YOUR_EMAILJS_PUBLIC_KEY_HERE",
   ```
   Replace with your Public Key:
   ```javascript
   publicKey: "pk-aBcDeFg123456",
   ```

3. Find line 30:
   ```javascript
   emailjs.send('YOUR_SERVICE_ID', 'YOUR_TEMPLATE_ID', templateParams)
   ```
   Replace with your Service ID and Template ID:
   ```javascript
   emailjs.send('service_abc123', 'template_xyz789', templateParams)
   ```

---

## Step 6: Test the Integration

1. **Start your server**:
   ```powershell
   python project_start_server.py --enforce-gpu --n-gpu-layers 40
   ```

2. **Register a new user**:
   - Go to: `http://localhost:7001/`
   - Click "Create one now"
   - Fill in the registration form
   - Use your **real email address**

3. **Check your email**:
   - You should receive a beautiful HTML email
   - With a 6-digit verification code
   - Within a few seconds

4. **Enter the code**:
   - Copy the 6-digit code from email
   - Paste it on the verification page
   - Your account will be created!

---

## Configuration Summary

After setup, your `verify_otp.html` should have:

```javascript
// Line 7-9: Initialize EmailJS
emailjs.init({
    publicKey: "YOUR_ACTUAL_PUBLIC_KEY",
});

// Line 30: Send email
emailjs.send('YOUR_SERVICE_ID', 'YOUR_TEMPLATE_ID', templateParams)
```

---

## Troubleshooting

### ❌ "Email not sent" error

**Solution**:
1. Check EmailJS dashboard for error logs
2. Verify Service ID and Template ID are correct
3. Ensure Public Key is correct
4. Check browser console for errors (F12)

### ❌ Email not received

**Solution**:
1. Check spam/junk folder
2. Verify email address is correct
3. Check EmailJS quota (200 emails/month on free plan)
4. Wait a few minutes (sometimes delayed)

### ❌ Template variables not showing

**Solution**:
1. In EmailJS template, use `{{variable_name}}` syntax
2. Variable names must match exactly:
   - `{{to_name}}` - recipient name
   - `{{otp_code}}` - verification code
   - `{{to_email}}` - recipient email

---

## Features & Limits

### ✅ What You Get (Free Plan):

- **200 emails/month** - Perfect for small projects
- **No domain verification** - Works immediately
- **Beautiful HTML emails** - Full styling support
- **Multiple email services** - Gmail, Outlook, Yahoo, etc.
- **Delivery tracking** - See if emails were sent
- **No credit card** - Completely free to start

### ⚠️ Limitations:

- **200 emails/month limit** - After that, you'll need to upgrade
- **EmailJS branding** - Small "Sent via EmailJS" footer
- **Client-side only** - Email is sent from browser (less secure than server-side)
- **Rate limiting** - Max 1 email per second

---

## How It Works

1. **User registers** → Server generates OTP code
2. **Page loads** → JavaScript sends email via EmailJS API
3. **User receives email** → With beautiful HTML template
4. **User enters code** → Account is verified and created

The OTP is sent both:
- ✉️ **To email** (via EmailJS)
- 🔗 **In URL parameter** (as backup for testing)

---

## Production Upgrade

When you exceed 200 emails/month or need more features:

**EmailJS Paid Plans**:
- **Starter**: $12/month - 2,000 emails
- **Pro**: $35/month - 10,000 emails
- **Business**: $70/month - 30,000 emails

**Or switch to server-side email**:
- Resend (requires domain verification)
- SendGrid
- Amazon SES
- Mailgun

---

## Quick Setup Checklist

- [ ] Create EmailJS account
- [ ] Add email service (Gmail/Outlook)
- [ ] Create email template with HTML
- [ ] Copy Service ID
- [ ] Copy Template ID
- [ ] Copy Public Key
- [ ] Update `verify_otp.html` with your IDs
- [ ] Test registration with real email
- [ ] Receive OTP email successfully
- [ ] Verify account creation works

---

## Support

- **EmailJS Docs**: https://www.emailjs.com/docs/
- **Dashboard**: https://dashboard.emailjs.com/
- **Free Plan Limits**: https://www.emailjs.com/pricing/

**Status**: ✅ EmailJS integration ready! Just add your credentials and test!

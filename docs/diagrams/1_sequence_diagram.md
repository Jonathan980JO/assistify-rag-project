# Sequence Diagram - User Login and Ticket Creation Flow

This diagram shows the **step-by-step interaction** between components when a user logs in and creates a support ticket.

## Mermaid Diagram (Copy this to render)

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant LoginServer
    participant Database
    participant SessionManager
    participant SecurityLogger
    
    %% Login Flow
    User->>Browser: Enter credentials
    Browser->>LoginServer: POST /login (username, password)
    LoginServer->>LoginServer: check_rate_limit(IP)
    LoginServer->>LoginServer: check_account_lockout(username)
    LoginServer->>Database: SELECT user WHERE username=?
    Database-->>LoginServer: User record
    LoginServer->>LoginServer: pwd_context.verify(password, hash)
    
    alt Password Correct
        LoginServer->>LoginServer: clear_failed_attempts(username)
        LoginServer->>LoginServer: create_session_token(username, role)
        LoginServer->>SessionManager: Track session (user_id, session_id)
        LoginServer->>SecurityLogger: log_security_event("login_success")
        LoginServer-->>Browser: Set SESSION_COOKIE, redirect to /main
        Browser-->>User: Show main page
    else Password Wrong
        LoginServer->>LoginServer: record_failed_login(username, IP)
        LoginServer->>SecurityLogger: log_security_event("login_failure")
        LoginServer-->>Browser: Error: Invalid credentials
        Browser-->>User: Show error message
    end
    
    %% Ticket Creation Flow
    User->>Browser: Click "Create Ticket"
    Browser->>LoginServer: GET /my-tickets
    LoginServer->>LoginServer: get_current_user(request)
    LoginServer->>LoginServer: validate_session(session_data)
    
    alt Session Valid
        LoginServer-->>Browser: Return ticket form
        Browser-->>User: Show ticket form
        
        User->>Browser: Fill form & submit
        Browser->>LoginServer: POST /api/tickets/create
        LoginServer->>LoginServer: verify_csrf(request)
        LoginServer->>LoginServer: validate_inputs()
        LoginServer->>Database: INSERT INTO support_tickets
        Database-->>LoginServer: ticket_id
        LoginServer->>Database: INSERT INTO notifications (for employees)
        LoginServer->>SecurityLogger: log_security_event("ticket_created")
        LoginServer-->>Browser: {status: "success", ticket_number}
        Browser-->>User: Show success message
    else Session Expired
        LoginServer-->>Browser: Redirect to /login
        Browser-->>User: Please log in again
    end
```

## How to Use This Diagram:

### Option 1: Render in VS Code
1. Install extension: **Markdown Preview Mermaid Support**
2. Open this file in VS Code
3. Press `Ctrl+Shift+V` (Preview)

### Option 2: Render Online
1. Go to: https://mermaid.live/
2. Copy the code between ` ```mermaid ` and ` ``` `
3. Paste and see the diagram

### Option 3: Export as Image
1. Use mermaid.live
2. Click "Actions" → "PNG" or "SVG"
3. Download the image

## What This Shows:

- **Login Security**: Rate limiting, account lockout, password verification
- **Session Management**: Token creation, validation
- **Security Logging**: All events tracked
- **CSRF Protection**: Token verification on ticket creation
- **Database Interactions**: Parameterized queries (safe from SQL injection)

## Components Explained:

- **LoginServer**: `Login_system/login_server.py` (your FastAPI app)
- **Database**: SQLite database with users, tickets, notifications
- **SessionManager**: Session timeout and concurrent session tracking
- **SecurityLogger**: JSON logs to `logs/security.log`

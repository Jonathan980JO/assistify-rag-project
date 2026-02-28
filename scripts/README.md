# Scripts Directory

This directory contains utility scripts, migration tools, and automation scripts for the Assistify project.

## Utility Scripts

### Security & OWASP
- **apply_owasp_fixes.py** - Automatically applies OWASP security fixes to HTML templates
  - Adds CSRF tokens
  - Replaces innerHTML with safeSetHTML
  - Adds security headers

### Database Migration
- **migrate_analytics.py** - Migrates analytics data between database versions
- **migrate_passwords.py** - Password migration and hash upgrade utility
- **inspect_passwords.py** - Password hash inspection and validation tool

### Server Management
- **project_start_server.py** - Project server startup script with proper initialization

### Testing Scripts
- **e2e_test_client.py** - End-to-end test client for WebSocket connections
- **e2e_test.py** - End-to-end system integration tests
- **import_test.py** - Import validation and module testing
- **test_ws_connect.py** - WebSocket connection testing

## Running Scripts

### Apply Security Fixes
```powershell
python scripts/apply_owasp_fixes.py
```

### Migrate Database
```powershell
python scripts/migrate_analytics.py
python scripts/migrate_passwords.py
```

### Start Server
```powershell
python scripts/project_start_server.py
```

### Run Tests
```powershell
python scripts/e2e_test.py
python scripts/test_ws_connect.py
```

## Script Categories

### 🔒 Security
- `apply_owasp_fixes.py` - OWASP security automation

### 💾 Database
- `migrate_analytics.py` - Analytics migration
- `migrate_passwords.py` - Password migration
- `inspect_passwords.py` - Password inspection

### 🚀 Server
- `project_start_server.py` - Server startup

### 🧪 Testing
- `e2e_test.py` - End-to-end tests
- `e2e_test_client.py` - Test client
- `test_ws_connect.py` - WebSocket tests
- `import_test.py` - Import tests

## Adding New Scripts

When creating new utility scripts:
1. Place in this `scripts/` directory
2. Add descriptive docstring at top of file
3. Update this README with script description and usage
4. Follow naming convention: `verb_noun.py` (e.g., `migrate_users.py`)

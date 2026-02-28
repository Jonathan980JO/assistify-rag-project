# Tests Directory

This directory contains all test files for the Assistify project.

## Test Files

### Security Tests
- **test_owasp_security.py** - OWASP Top 10 security audit for all HTML templates
- **test_owasp_final.py** - Final OWASP security validation tests
- **test_validation.py** - Input validation and response validation tests

### System Tests
- **test_system_integrity.py** - Overall system integrity checks
- **test_edge_cases.py** - Edge case testing for various components
- **test_400_debug.py** - Debug tests for 400 error responses

### TOON Tests
- **test_toon.py** - Unit tests for TOON (Token-Oriented Object Notation) implementation
- **test_toon_integration.py** - Integration tests for TOON in RAG system

## Running Tests

### Run Individual Test
```powershell
python tests/test_toon.py
```

### Run All Tests
```powershell
Get-ChildItem tests/test_*.py | ForEach-Object { python $_.FullName }
```

### Run Specific Test Category
```powershell
# Security tests
python tests/test_owasp_security.py

# TOON tests
python tests/test_toon.py
python tests/test_toon_integration.py
```

## Test Coverage

- ✅ OWASP Top 10 security compliance
- ✅ TOON format encoding/decoding
- ✅ RAG system integration
- ✅ Input validation
- ✅ System integrity

## Adding New Tests

When creating new tests:
1. Name files with `test_` prefix
2. Place in this `tests/` directory
3. Update imports to reference parent directory:
   ```python
   project_root = Path(__file__).parent.parent
   sys.path.insert(0, str(project_root))
   ```
4. Update this README with test description

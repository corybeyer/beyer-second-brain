---
description: "Security review of code changes"
---

Perform a security review of the files I created or modified in this session.

## Check for These Issues

### 1. Hardcoded Secrets
- API keys, passwords, tokens
- Connection strings with credentials
- Any string that looks like a secret

### 2. Injection Vulnerabilities
- SQL injection (string concatenation in queries)
- Command injection (user input in shell commands)
- Path traversal (user input in file paths)

### 3. Dangerous Functions
- `eval()`, `exec()` — arbitrary code execution
- `os.system()`, `subprocess` with `shell=True`
- `pickle.load()` on untrusted data

### 4. Data Exposure
- Logging sensitive data
- Returning secrets in error messages
- Overly permissive file permissions

### 5. Dependency Issues
- Known vulnerable packages
- Unpinned dependencies that could change

## Response Format

For each file:
```
path/to/file.py
  ✓ No issues found
  — OR —
  ✗ ISSUES:
    - Line X: [SEVERITY] Description
    - Line Y: [SEVERITY] Description
```

Severity levels: CRITICAL, HIGH, MEDIUM, LOW

End with: "Security review complete. X critical, Y high, Z medium issues."

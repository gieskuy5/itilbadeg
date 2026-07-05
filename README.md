# itilbadeg

Interlink Auto-Mining Bot — auto login, claim mine, token refresh.

## Files

| File | Description |
|------|-------------|
| `main.py` | Main bot script |
| `run.sh` | Auto-restart wrapper |
| `accounts.example.txt` | Account format example |
| `proxy.example.txt` | Proxy format example |
| `config.example.txt` | Config reference |

## Setup

```bash
# 1. Create accounts.txt
cp accounts.example.txt accounts.txt
# Edit with your: loginId|passcode|gmail|gmail_app_password

# 2. (Optional) Create proxy.txt
cp proxy.example.txt proxy.txt
# Add proxies

# 3. Run
python3 main.py

# Or with auto-restart:
bash run.sh
```

## Features

- Auto login via Gmail OTP (IMAP)
- Auto claim mine every 4 hours
- Auto token refresh (JWT)
- Persistent device fingerprint (sessions.json)
- Proxy support
- Human-like delays

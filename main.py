import requests
import json
import time
import base64
import imaplib
import email
import re
import os
import sys
import random
import uuid
import tempfile
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== CONFIG ====================
BASE_URL = "https://prod.interlinklabs.ai"
APP_VERSION = "4.0.3"
USER_AGENT = "okhttp/4.12.0"
BUNDLE_ID = "org.ai.interlinklabs.interlinkId"
SYSTEM_NAME = "Android"

# Gmail IMAP settings
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
OTP_POLL_INTERVAL = 5   # seconds between checks
OTP_POLL_TIMEOUT = 120  # max seconds to wait for OTP

# Device models for fingerprinting — (model, brand, typical screen resolution)
DEVICE_MODELS = [
    ("Redmi Note 5",  "Xiaomi",  "1080x2160"),
    ("Redmi Note 8",  "Xiaomi",  "1080x2340"),
    ("Redmi Note 9",  "Xiaomi",  "1080x2340"),
    ("Redmi Note 10", "Xiaomi",  "1080x2400"),
    ("Redmi Note 11", "Xiaomi",  "1080x2400"),
    ("Galaxy A52",    "Samsung", "1080x2400"),
    ("Galaxy A53",    "Samsung", "1080x2400"),
    ("Galaxy S21",    "Samsung", "1080x2400"),
    ("Pixel 5",       "Google",  "1080x2340"),
    ("Pixel 6",       "Google",  "1080x2400"),
    ("POCO X3",       "Xiaomi",  "1080x2400"),
    ("POCO F3",       "Xiaomi",  "1080x2400"),
    ("OnePlus 9",     "OnePlus", "1080x2400"),
    ("Realme 8",      "Realme",  "1080x2400"),
    ("Vivo V21",      "Vivo",    "1080x2404"),
]

# Realistic Android build IDs
BUILD_IDS = [
    "TP1A.220624.014", "SP1A.210812.016", "RQ3A.211001.001",
    "SKQ1.211006.001", "TKQ1.220829.002", "TP1A.220905.004",
    "UKQ1.230804.001", "TQ3A.230901.001", "AP1A.240505.005",
    "UP1A.231005.007", "TD1A.221105.003", "SKQ1.220303.001",
]

SCREEN_DENSITIES = [2.0, 2.625, 2.75, 3.0, 3.5]

# ==================== COLORS ====================
class Colors:
    RESET   = "\033[0m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

def log_info(msg, account=""):
    prefix = f"{Colors.CYAN}[{account}]{Colors.RESET} " if account else ""
    print(f"{Colors.BLUE}[{datetime.now().strftime('%H:%M:%S')}]{Colors.RESET} {prefix}{Colors.WHITE}{msg}{Colors.RESET}")

def log_success(msg, account=""):
    prefix = f"{Colors.CYAN}[{account}]{Colors.RESET} " if account else ""
    print(f"{Colors.GREEN}[{datetime.now().strftime('%H:%M:%S')}]{Colors.RESET} {prefix}{Colors.GREEN}✓ {msg}{Colors.RESET}")

def log_warning(msg, account=""):
    prefix = f"{Colors.CYAN}[{account}]{Colors.RESET} " if account else ""
    print(f"{Colors.YELLOW}[{datetime.now().strftime('%H:%M:%S')}]{Colors.RESET} {prefix}{Colors.YELLOW}⚠ {msg}{Colors.RESET}")

def log_error(msg, account=""):
    prefix = f"{Colors.CYAN}[{account}]{Colors.RESET} " if account else ""
    print(f"{Colors.RED}[{datetime.now().strftime('%H:%M:%S')}]{Colors.RESET} {prefix}{Colors.RED}✗ {msg}{Colors.RESET}")

def log_step(step, msg, account=""):
    prefix = f"{Colors.CYAN}[{account}]{Colors.RESET} " if account else ""
    print(f"{Colors.MAGENTA}[{datetime.now().strftime('%H:%M:%S')}]{Colors.RESET} {prefix}{Colors.BOLD}[Step {step}]{Colors.RESET} {Colors.WHITE}{msg}{Colors.RESET}")

# ==================== SESSION ====================
def create_session(proxy=None):
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session

# ==================== DEVICE FINGERPRINT ====================
def generate_device_fingerprint():
    """
    Generate a realistic Android device fingerprint.
    This is called ONCE per account and then persisted in sessions.json.
    """
    device_id = ''.join(random.choices('0123456789abcdef', k=16))
    android_id = ''.join(random.choices('0123456789abcdef', k=16))
    model, brand, screen_res = random.choice(DEVICE_MODELS)
    os_version = str(random.randint(10, 14))
    build_id = random.choice(BUILD_IDS)
    density = random.choice(SCREEN_DENSITIES)
    app_install_id = str(uuid.uuid4())

    return {
        "device_id": device_id,
        "model": model,
        "brand": brand,
        "os_version": os_version,
        "android_id": android_id,
        "build_id": build_id,
        "screen_density": density,
        "screen_resolution": screen_res,
        "app_install_id": app_install_id,
        "locale": "en_US",
        "timezone": "Asia/Jakarta",
    }

# ==================== API HELPERS ====================
def build_headers(device):
    """Build request headers matching the Interlink mobile app."""
    return {
        "accept": "*/*",
        "version": APP_VERSION,
        "x-unique-id": device["device_id"],
        "x-model": device["model"],
        "x-brand": device["brand"],
        "x-system-name": SYSTEM_NAME,
        "x-device-id": device["device_id"],
        "x-bundle-id": BUNDLE_ID,
        "user-agent": USER_AGENT,
    }

def make_get_request(session, url, device, auth_token=None, params=None, label=""):
    """Make a GET request."""
    headers = build_headers(device)
    if auth_token:
        headers["authorization"] = f"Bearer {auth_token}"

    for attempt in range(3):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=(10, 30))
            return resp.json()
        except requests.exceptions.Timeout:
            log_warning(f"GET timeout (attempt {attempt+1}/3), retrying...", label)
            time.sleep(2 ** attempt)
        except Exception as e:
            log_warning(f"GET error (attempt {attempt+1}/3): {e}", label)
            time.sleep(2 ** attempt)
    return {"error": "All retry attempts failed"}

def make_post_request(session, url, body_dict, device, auth_token=None, label=""):
    """Make a POST request."""
    body_str = json.dumps(body_dict, separators=(',', ':'))
    headers = build_headers(device)
    headers["content-type"] = "application/json"
    if auth_token:
        headers["authorization"] = f"Bearer {auth_token}"

    for attempt in range(3):
        try:
            resp = session.post(url, data=body_str, headers=headers, timeout=(10, 30))
            return resp.json()
        except requests.exceptions.Timeout:
            log_warning(f"POST timeout (attempt {attempt+1}/3), retrying...", label)
            time.sleep(2 ** attempt)
        except Exception as e:
            log_warning(f"POST error (attempt {attempt+1}/3): {e}", label)
            time.sleep(2 ** attempt)
    return {"error": "All retry attempts failed"}

# ==================== GMAIL OTP RETRIEVAL ====================
def get_last_interlink_email_id(gmail_address, app_password, account_label=""):
    """
    Get the ID of the most recent Interlink email currently in the inbox.
    Call this BEFORE sending the OTP request to snapshot the state.
    Returns the email ID (as bytes) or None if no Interlink emails exist.
    """
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(gmail_address, app_password)
        mail.select("INBOX")

        status, messages = mail.search(None, '(FROM "noreply@interlinklabs.org")')

        last_id = None
        if status == "OK" and messages[0]:
            email_ids = messages[0].split()
            last_id = email_ids[-1]
            log_info(f"Last known Interlink email ID: {last_id.decode()}", account_label)
        else:
            log_info("No previous Interlink emails in inbox", account_label)

        mail.logout()
        return last_id
    except Exception as e:
        log_warning(f"Could not snapshot email state: {e}", account_label)
        return None


def get_otp_from_gmail(gmail_address, app_password, account_label="", last_known_id=None):
    """
    Connect to Gmail via IMAP and retrieve the NEW OTP code from Interlink.
    Only considers emails with IDs greater than last_known_id (emails that arrived
    after the OTP was requested). If last_known_id is None, falls back to getting
    the very latest email.
    """
    log_info("Waiting for NEW OTP email from Interlink...", account_label)
    start_time = time.time()

    while time.time() - start_time < OTP_POLL_TIMEOUT:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(gmail_address, app_password)
            mail.select("INBOX")

            # Search for emails from Interlink sender
            status, messages = mail.search(None, '(FROM "noreply@interlinklabs.org")')

            if status != "OK" or not messages[0]:
                mail.logout()
                log_info(f"No Interlink emails found, retrying in {OTP_POLL_INTERVAL}s...", account_label)
                time.sleep(OTP_POLL_INTERVAL)
                continue

            email_ids = messages[0].split()

            # Filter to only NEW emails (IDs greater than last_known_id)
            if last_known_id is not None:
                new_ids = [eid for eid in email_ids if int(eid) > int(last_known_id)]
            else:
                # Fallback: just take the latest one
                new_ids = [email_ids[-1]]

            if not new_ids:
                mail.logout()
                log_info(f"No new Interlink emails yet, retrying in {OTP_POLL_INTERVAL}s...", account_label)
                time.sleep(OTP_POLL_INTERVAL)
                continue

            # Get the LATEST new email (last in list = newest)
            latest_eid = new_ids[-1]
            log_info(f"Found new email ID: {latest_eid.decode()}", account_label)
            status, msg_data = mail.fetch(latest_eid, "(RFC822)")

            if status == "OK":
                msg = email.message_from_bytes(msg_data[0][1])

                email_date = msg.get("Date", "")
                log_info(f"New Interlink email date: {email_date}", account_label)

                # Extract body — prefer text/plain, fall back to text/html
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain":
                            body_text = part.get_payload(decode=True).decode(errors="ignore")
                            break
                        elif ct == "text/html":
                            body_text = part.get_payload(decode=True).decode(errors="ignore")
                else:
                    body_text = msg.get_payload(decode=True).decode(errors="ignore")

                # Extract 6-digit OTP code
                otp_match = re.search(r'\b(\d{6})\b', body_text)
                if otp_match:
                    otp = otp_match.group(1)
                    log_success(f"OTP found: {otp}", account_label)
                    mail.logout()
                    return otp
                else:
                    log_warning("Email found but no 6-digit OTP in body, retrying...", account_label)

            mail.logout()
        except imaplib.IMAP4.error as e:
            log_error(f"IMAP error: {e}", account_label)
        except Exception as e:
            log_error(f"Email check error: {e}", account_label)

        time.sleep(OTP_POLL_INTERVAL)

    log_error(f"OTP retrieval timed out after {OTP_POLL_TIMEOUT}s", account_label)
    return None

# ==================== LOGIN FLOW ====================
def login_account(login_id, passcode, gmail_address, app_password, device, proxy=None):
    """
    Execute the full Interlink login flow:
    1. Check if loginId exists
    2. Verify passcode
    3. Send OTP email
    4. Retrieve OTP from Gmail
    5. Verify OTP → get JWT token
    """
    label = login_id
    session = create_session(proxy)

    print(f"\n{'='*60}")
    log_info(f"{Colors.BOLD}Starting login for account {login_id}{Colors.RESET}", label)
    if proxy:
        log_info(f"Using proxy: {proxy[:40]}...", label)
    print(f"{'='*60}")

    # ── Step 1: Check loginId exists ──
    log_step(1, "Checking if loginId exists...", label)
    url = f"{BASE_URL}/api/v1/auth/loginId-exist-check/{login_id}"
    params = {"deviceId": device["device_id"]}
    result = make_get_request(session, url, device, params=params, label=label)

    if "error" in result:
        log_error(f"Request failed: {result['error']}", label)
        return None
    if result.get("data") is not True:
        log_error(f"LoginId {login_id} does not exist!", label)
        return None
    log_success("LoginId verified", label)
    time.sleep(random.uniform(1, 2))

    # ── Step 2: Check passcode ──
    log_step(2, "Verifying passcode...", label)
    url = f"{BASE_URL}/api/v1/auth/check-passcode"
    body = {
        "loginId": login_id,
        "passcode": passcode,
        "deviceId": device["device_id"],
    }
    result = make_post_request(session, url, body, device, label=label)

    if "error" in result:
        log_error(f"Request failed: {result['error']}", label)
        return None
    if result.get("statusCode") != 200:
        log_error(f"Passcode check failed: {result.get('message', 'Unknown error')}", label)
        return None

    user_data = result.get("data", {})
    user_email = user_data.get("email", gmail_address)
    log_success(f"Passcode verified — email: {user_email}", label)
    time.sleep(random.uniform(1, 2))

    # ── Step 3: Snapshot email state & Send OTP email ──
    # Snapshot the last known email ID BEFORE requesting OTP
    last_email_id = get_last_interlink_email_id(gmail_address, app_password, label)

    log_step(3, f"Sending OTP to {gmail_address}...", label)
    url = f"{BASE_URL}/api/v1/auth/send-otp-email-verify-login"
    body = {
        "loginId": login_id,
        "passcode": passcode,
        "email": gmail_address,
        "deviceId": device["device_id"],
    }
    result = make_post_request(session, url, body, device, label=label)

    if "error" in result:
        log_error(f"Request failed: {result['error']}", label)
        return None
    if result.get("statusCode") != 200:
        log_error(f"Send OTP failed: {result.get('message', 'Unknown error')}", label)
        return None
    log_success(f"OTP email sent to {gmail_address}", label)

    # ── Step 4: Retrieve NEW OTP from Gmail ──
    log_step(4, "Retrieving NEW OTP from Gmail...", label)
    time.sleep(5)
    otp = get_otp_from_gmail(gmail_address, app_password, label, last_known_id=last_email_id)

    if not otp:
        log_error("Failed to retrieve OTP from Gmail", label)
        return None

    # ── Step 5: Verify OTP ──
    log_step(5, f"Verifying OTP: {otp}...", label)
    url = f"{BASE_URL}/api/v1/auth/check-otp-email-verify-login"
    body = {
        "loginId": login_id,
        "otp": otp,
        "deviceId": device["device_id"],
    }
    result = make_post_request(session, url, body, device, label=label)

    if "error" in result:
        log_error(f"Request failed: {result['error']}", label)
        return None
    if result.get("statusCode") != 200:
        log_error(f"OTP verification failed: {result.get('message', 'Unknown error')}", label)
        return None

    # Debug: log full response
    log_info(f"OTP verify response: {json.dumps(result)[:200]}", label)
    
    # API returns accessToken, not jwtToken
    jwt_token = result.get("data", {}).get("accessToken") or result.get("data", {}).get("jwtToken")
    if jwt_token:
        log_success(f"Login successful! JWT token received", label)
        log_info(f"Token: {jwt_token[:50]}...", label)
        return jwt_token
    else:
        log_error(f"No JWT token in response: {result.get('message', 'Unknown')}", label)
        return None

# ==================== FILE HELPERS ====================
def load_accounts(filepath):
    """Load accounts from file. Format: loginId|passcode|gmail|gmail_app_password"""
    accounts = []
    if not os.path.exists(filepath):
        log_error(f"Accounts file not found: {filepath}")
        return accounts

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 4:
                log_warning(f"Skipping invalid line {line_num}: expected loginId|passcode|gmail|app_password")
                continue
            accounts.append({
                "login_id": parts[0].strip(),
                "passcode": parts[1].strip(),
                "gmail": parts[2].strip(),
                "app_password": parts[3].strip(),
            })
    return accounts

def load_proxies(filepath):
    """Load proxies from file. One proxy per line."""
    proxies = []
    if not os.path.exists(filepath):
        return proxies
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if not line.startswith("http"):
                    line = f"http://{line}"
                proxies.append(line)
    return proxies

def save_token(filepath, login_id, token):
    """Save/update a token in the tokens file (overwrites if loginId exists)."""
    lines = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

    # Remove old entry for this login_id
    lines = [l for l in lines if not l.startswith(f"{login_id}|")]
    lines.append(f"{login_id}|{token}\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)

def load_tokens(filepath):
    """Load saved tokens from file. Returns dict of {loginId: token}."""
    tokens = {}
    if not os.path.exists(filepath):
        return tokens
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "|" not in line:
                continue
            parts = line.split("|", 1)
            if len(parts) == 2:
                tokens[parts[0].strip()] = parts[1].strip()
    return tokens

# ==================== SESSION PERSISTENCE ====================
def load_sessions(filepath):
    """Load saved device sessions from sessions.json."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log_warning(f"Could not load sessions file: {e}")
        return {}

def save_sessions(filepath, sessions):
    """Atomically save sessions dict to sessions.json (write to temp then rename)."""
    dir_name = os.path.dirname(filepath) or "."
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)
        # On Windows, need to remove target first if it exists
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(tmp_path, filepath)
    except Exception as e:
        log_error(f"Failed to save sessions: {e}")
        # Clean up temp file on failure
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

def get_or_create_session(sessions, login_id, sessions_file):
    """
    Get the persistent device fingerprint for a login_id.
    If none exists, generate one and save it immediately.
    Returns the device dict.
    """
    key = f"account_{login_id}"
    if key in sessions:
        device = sessions[key]["device"]
        log_success(f"Loaded saved session (device: {device['model']} / {device['device_id'][:8]}...)", login_id)
        return device

    # Generate new fingerprint for this account
    log_info(f"No saved session found, generating new device fingerprint...", login_id)
    device = generate_device_fingerprint()
    sessions[key] = {
        "login_id": login_id,
        "device": device,
        "created_at": datetime.now().isoformat(),
        "last_login": None,
    }
    save_sessions(sessions_file, sessions)
    log_success(f"New session created (device: {device['model']} / {device['device_id'][:8]}...)", login_id)
    return device

def update_session_login_time(sessions, login_id, sessions_file):
    """Update the last_login timestamp for an account session."""
    key = f"account_{login_id}"
    if key in sessions:
        sessions[key]["last_login"] = datetime.now().isoformat()
        save_sessions(sessions_file, sessions)

# ==================== JWT HELPERS ====================
def decode_jwt_payload(token):
    """Decode JWT payload (without verification) to read claims like exp."""
    try:
        payload_b64 = token.split(".")[1]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_json = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_json)
    except Exception:
        return None

def get_token_expiry(token):
    """Get the expiration timestamp from a JWT token. Returns epoch seconds or None."""
    payload = decode_jwt_payload(token)
    if payload and "exp" in payload:
        return payload["exp"]
    return None

def is_token_expired(token, buffer_seconds=300):
    """
    Check if a JWT token is expired or will expire within buffer_seconds.
    Default buffer is 5 minutes (300s) so we re-login before actual expiry.
    """
    exp = get_token_expiry(token)
    if exp is None:
        return True  # Can't determine expiry, treat as expired
    return time.time() >= (exp - buffer_seconds)

def get_token_remaining(token):
    """Get remaining time in seconds before token expires."""
    exp = get_token_expiry(token)
    if exp is None:
        return 0
    return max(0, exp - time.time())

# ==================== MINING API ====================
def get_user_context(session, token, device, label=""):
    """
    Get user context including claim status and token balance.
    Returns dict with keys: isClaimable, nextFrame, lastClaimTime, goldTokens, hashRate, or None on failure.
    """
    url = f"{BASE_URL}/api/v1/auth/current-user-full"
    params = {"include": "userInfo,token,isClaimable"}
    result = make_get_request(session, url, device, auth_token=token, params=params, label=label)

    if "error" in result:
        log_error(f"Failed to get user context: {result['error']}", label)
        return None
    if result.get("statusCode") == 401:
        log_warning("Token rejected (401), need re-login", label)
        return {"auth_failed": True}
    if result.get("statusCode") != 200:
        log_error(f"User context error: {result.get('message', 'Unknown')}", label)
        return None

    data = result.get("data", {})
    token_info = data.get("token", {})
    claimable_info = data.get("isClaimable", {})

    # Normalize nextFrame to epoch ms (API may return seconds or milliseconds)
    raw_next = claimable_info.get("nextFrame", 0)
    next_frame_ms = raw_next * 1000 if raw_next and raw_next < 10000000000 else raw_next

    raw_lct = token_info.get("lastClaimTime", 0)
    last_claim_ms = raw_lct * 1000 if raw_lct and raw_lct < 10000000000 else raw_lct

    return {
        "isClaimable": claimable_info.get("isClaimable", False),
        "nextFrame": next_frame_ms,  # always epoch ms
        "lastClaimTime": last_claim_ms,
        "goldTokens": token_info.get("interlinkGoldTokenAmount", 0),
        "hashRate": token_info.get("dailyMiningRate", 0),
        "baseReward": token_info.get("baseReward", 0),
        "totalHhp": token_info.get("directReferralsHashRate", 0) + token_info.get("indirectReferralsHashRate", 0),
    }


def claim_mine(session, token, device, label=""):
    """
    Claim the mine airdrop.
    Returns the reward amount on success, None on failure, or 'auth_failed' on 401.
    """
    url = f"{BASE_URL}/api/v1/token/claim-airdrop"
    headers = build_headers(device)
    headers["authorization"] = f"Bearer {token}"
    headers["content-length"] = "0"

    for attempt in range(3):
        try:
            resp = session.post(url, headers=headers, timeout=(10, 30))
            result = resp.json()

            if result.get("statusCode") == 401:
                log_warning("Token rejected (401) during claim, need re-login", label)
                return "auth_failed"
            if result.get("statusCode") == 400:
                msg = result.get("message", "")
                if "TOO_EARLY" in msg:
                    log_warning("Claim too early — not yet claimable", label)
                    return "too_early"
                log_error(f"Claim failed: {msg}", label)
                return None
            if result.get("statusCode") == 200:
                reward = result.get("data", 0)
                return reward

            log_warning(f"Unexpected claim response: {result}", label)
            return None
        except requests.exceptions.Timeout:
            log_warning(f"Claim timeout (attempt {attempt+1}/3), retrying...", label)
            time.sleep(2 ** attempt)
        except Exception as e:
            log_warning(f"Claim error (attempt {attempt+1}/3): {e}", label)
            time.sleep(2 ** attempt)

    return None


def do_relogin(state, tokens_file, sessions=None, sessions_file=None):
    """
    Helper to perform re-login for an account state. Returns True on success.
    Keeps the SAME device fingerprint — a real phone doesn't change hardware on re-login.
    """
    acc = state["account"]
    lid = acc["login_id"]
    log_warning("Performing re-login (keeping same device)...", lid)
    # DO NOT regenerate device — reuse the persistent one
    new_token = login_account(
        lid, acc["passcode"], acc["gmail"], acc["app_password"],
        state["device"], state["proxy"]
    )
    if new_token:
        state["token"] = new_token
        save_token(tokens_file, lid, new_token)
        if sessions is not None and sessions_file:
            update_session_login_time(sessions, lid, sessions_file)
        remaining = get_token_remaining(new_token)
        log_success(f"Re-login successful! Token valid for {remaining/60:.0f} minutes", lid)
        return True
    else:
        log_error("Re-login failed, will retry next cycle", lid)
        state["token"] = None
        return False


# ==================== BANNER ====================
def print_banner():
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
  ╔══════════════════════════════════════════════════╗
  ║          INTERLINK AUTO-MINING BOT               ║
  ║      Auto Login • Claim • Token Refresh          ║
  ╚══════════════════════════════════════════════════╝
{Colors.RESET}
{Colors.DIM}  Endpoints: prod.interlinklabs.ai
  Flow: Login → Check Claimable → Claim Mine → Wait → Repeat
  OTP Source: Gmail IMAP (App Password){Colors.RESET}
"""
    print(banner)

# ==================== MAIN ====================
MINE_CHECK_INTERVAL = 30  # Seconds between mine status checks

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Load accounts
    accounts_file = os.path.join(script_dir, "accounts.txt")
    accounts = load_accounts(accounts_file)
    if not accounts:
        log_error(f"No accounts found in {accounts_file}")
        log_info("Format: loginId|passcode|gmail|gmail_app_password")
        log_info("Example: yourloginId|yourpasscode|example@gmail.com|xxxx-xxxx-xxxx-xxxx")
        return

    log_success(f"Loaded {len(accounts)} account(s)")

    # Load proxies
    proxy_file = os.path.join(script_dir, "proxy.txt")
    proxies = load_proxies(proxy_file)
    if proxies:
        log_success(f"Loaded {len(proxies)} proxy(s)")
    else:
        log_warning("No proxies loaded — running without proxy")

    # Token output file
    tokens_file = os.path.join(script_dir, "tokens.txt")

    # Sessions file — persistent device fingerprints
    sessions_file = os.path.join(script_dir, "sessions.json")
    sessions = load_sessions(sessions_file)
    if sessions:
        log_success(f"Loaded {len(sessions)} saved session(s) from sessions.json")
    else:
        log_info("No saved sessions found, will generate new device fingerprints")

    # Load existing tokens
    saved_tokens = load_tokens(tokens_file)
    if saved_tokens:
        log_info(f"Found {len(saved_tokens)} saved token(s) in tokens.txt")

    # State per account — use persistent device fingerprint from sessions.json
    account_states = []
    for i, account in enumerate(accounts):
        proxy = proxies[i % len(proxies)] if proxies else None
        # Get or create a PERSISTENT device fingerprint for this account
        device = get_or_create_session(sessions, account["login_id"], sessions_file)
        account_states.append({
            "account": account,
            "device": device,
            "proxy": proxy,
            "token": None,
            "login_id": account["login_id"],
            "session": create_session(proxy),
            "next_claim_time": 0,  # epoch ms when next claim is possible
        })

    # ── Load saved tokens or login ──
    for state in account_states:
        acc = state["account"]
        lid = acc["login_id"]

        # Check if we have a saved token that's still valid
        saved = saved_tokens.get(lid)
        if saved and not is_token_expired(saved):
            remaining = get_token_remaining(saved)
            log_success(f"Using saved token (valid for {remaining/60:.0f} minutes)", lid)
            state["token"] = saved
        else:
            if saved:
                log_warning("Saved token expired, logging in...", lid)
            else:
                log_info("No saved token, logging in...", lid)

            token = login_account(
                lid, acc["passcode"], acc["gmail"], acc["app_password"],
                state["device"], state["proxy"]
            )

            if token:
                state["token"] = token
                save_token(tokens_file, lid, token)
                update_session_login_time(sessions, lid, sessions_file)
                remaining = get_token_remaining(token)
                log_success(f"Login successful! Token valid for {remaining/60:.0f} minutes", lid)
            else:
                log_error("Login failed, will retry in mining loop", lid)

        # Delay between accounts
        if len(account_states) > 1 and state != account_states[-1]:
            time.sleep(random.uniform(1, 3))

    log_info("Entering mining loop...")

    while True:
        try:
            earliest_next = None  # Track the earliest nextFrame across all accounts

            for state in account_states:
                acc = state["account"]
                lid = acc["login_id"]
                token = state["token"]
                session = state["session"]

                # ── No token → re-login ──
                if token is None:
                    do_relogin(state, tokens_file, sessions, sessions_file)
                    token = state["token"]
                    if token is None:
                        continue

                # ── Token expiry check ──
                if is_token_expired(token):
                    log_warning(f"Token expired or expiring soon, need re-login", lid)
                    if not do_relogin(state, tokens_file, sessions, sessions_file):
                        continue
                    token = state["token"]

                # ── Check claim status ──
                log_info("Checking mine claim status...", lid)
                ctx = get_user_context(session, token, state["device"], lid)

                if ctx is None:
                    log_error("Could not get user context, will retry", lid)
                    continue

                if ctx.get("auth_failed"):
                    if not do_relogin(state, tokens_file, sessions, sessions_file):
                        continue
                    token = state["token"]
                    ctx = get_user_context(session, token, state["device"], lid)
                    if ctx is None or ctx.get("auth_failed"):
                        continue

                gold = ctx.get("goldTokens", 0)
                hash_rate = ctx.get("hashRate", 0)
                is_claimable = ctx.get("isClaimable", False)
                next_frame = ctx.get("nextFrame", 0)

                log_info(f"Gold: {Colors.YELLOW}{gold}{Colors.RESET} | Hash Rate: {hash_rate} | Claimable: {is_claimable}", lid)

                if is_claimable:
                    # ── CLAIM THE MINE ──
                    log_step("⛏", f"{Colors.BOLD}Claiming mine...{Colors.RESET}", lid)
                    result = claim_mine(session, token, state["device"], lid)

                    if result == "auth_failed":
                        if do_relogin(state, tokens_file, sessions, sessions_file):
                            token = state["token"]
                            result = claim_mine(session, token, state["device"], lid)

                    if result == "too_early":
                        log_warning("Server says claim too early, will wait", lid)
                    elif result is not None and result != "auth_failed":
                        log_success(f"Mine claimed! Reward: {Colors.YELLOW}{Colors.BOLD}{result}{Colors.RESET}{Colors.GREEN} gold tokens{Colors.RESET}", lid)

                        # Re-check context to get updated nextFrame
                        time.sleep(2)
                        ctx_new = get_user_context(session, token, state["device"], lid)
                        if ctx_new and not ctx_new.get("auth_failed"):
                            next_frame = ctx_new.get("nextFrame", 0)
                            new_gold = ctx_new.get("goldTokens", 0)
                            log_info(f"Updated balance: {Colors.YELLOW}{new_gold}{Colors.RESET} gold", lid)
                    else:
                        log_error("Mine claim failed", lid)

                # ── Calculate wait time ──
                if next_frame > 0:
                    now_ms = int(time.time() * 1000)
                    wait_ms = next_frame - now_ms
                    if wait_ms > 0:
                        wait_sec = wait_ms / 1000
                        hours = int(wait_sec // 3600)
                        minutes = int((wait_sec % 3600) // 60)
                        secs = int(wait_sec % 60)
                        time_str = ""
                        if hours > 0:
                            time_str += f"{hours}h "
                        if minutes > 0:
                            time_str += f"{minutes}m "
                        time_str += f"{secs}s"
                        claim_at = datetime.fromtimestamp(next_frame / 1000).strftime('%H:%M:%S')
                        log_info(f"Next mine claim in: {Colors.CYAN}{Colors.BOLD}{time_str}{Colors.RESET} (opens at {claim_at})", lid)
                        state["next_claim_time"] = next_frame

                        if earliest_next is None or next_frame < earliest_next:
                            earliest_next = next_frame
                    else:
                        log_info("Mine should be claimable now!", lid)
                        if earliest_next is None:
                            earliest_next = now_ms
                else:
                    if not is_claimable:
                        log_info("No next frame info available, will check again soon", lid)

                # Small delay between accounts
                if len(account_states) > 1 and state != account_states[-1]:
                    time.sleep(random.uniform(1, 3))

            # ── Live countdown until next check (human-like delay) ──
            if earliest_next is not None:
                now_ms = int(time.time() * 1000)
                sleep_ms = earliest_next - now_ms
                if sleep_ms > 0:
                    sleep_sec = sleep_ms / 1000
                    # Human-like delay: wait 30s + random 1-60s after claim window
                    human_delay = 30 + random.randint(1, 60)
                    sleep_sec = sleep_sec + human_delay
                    log_info(f"Adding {human_delay}s human delay after claim window")
                    end_time = time.time() + sleep_sec
                    is_tty = sys.stdout.isatty()
                    try:
                        last_log = 0
                        while True:
                            remaining = end_time - time.time()
                            if remaining <= 0:
                                break
                            h = int(remaining // 3600)
                            m = int((remaining % 3600) // 60)
                            s = int(remaining % 60)
                            parts = []
                            if h > 0:
                                parts.append(f"{h}h")
                            if m > 0:
                                parts.append(f"{m}m")
                            parts.append(f"{s}s")
                            time_str = " ".join(parts)
                            if is_tty:
                                # Live countdown for interactive terminals
                                print(f"\r{Colors.BLUE}[{datetime.now().strftime('%H:%M:%S')}]{Colors.RESET} {Colors.WHITE}⏳ Next check in: {Colors.CYAN}{Colors.BOLD}{time_str}{Colors.RESET}   ", end="", flush=True)
                            else:
                                # VPS/log mode: print every 5 minutes
                                now_min = int(remaining // 60)
                                if now_min != last_log and now_min % 5 == 0:
                                    last_log = now_min
                                    log_info(f"⏳ Next check in: {time_str}")
                            time.sleep(1)
                    except KeyboardInterrupt:
                        if is_tty:
                            print()
                        raise
                    if is_tty:
                        print()  # newline after countdown
                else:
                    time.sleep(MINE_CHECK_INTERVAL)
            else:
                time.sleep(MINE_CHECK_INTERVAL)

        except KeyboardInterrupt:
            print(f"\n{'='*60}")
            log_info(f"{Colors.BOLD}Bot stopped by user (Ctrl+C){Colors.RESET}")
            log_info(f"Tokens saved to: {tokens_file}")
            log_info(f"Sessions saved to: {sessions_file}")
            print(f"{'='*60}\n")
            break
        except Exception as e:
            log_error(f"Unexpected error in mining loop: {e}")
            log_info("Retrying in 30 seconds...")
            time.sleep(30)

if __name__ == "__main__":
    main()
import os
import sqlite3
import binascii
import json
import subprocess
from datetime import datetime
from Crypto.Cipher import AES
from logging_folder import get_logger

log = get_logger(__name__)

def kill_chrome_processes():
    try:
        log.info("Terminating all chrome.exe processes...")
        subprocess.run(
            ["taskkill", "/F", "/IM", "chrome.exe"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        log.info("All chrome.exe processes have been terminated.")
    except Exception as e:
        log.error(f"Error terminating Chrome processes: {e!r}")

def open_chrome():
    try:
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not os.path.exists(chrome_path):
            chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        if os.path.exists(chrome_path):
            subprocess.Popen([chrome_path])
            log.info("Chrome restarted.")
        else:
            log.warning("chrome.exe not found for auto-restart.")
    except Exception as e:
        log.error(f"Error starting Chrome: {e!r}")

def is_file_modified_today(path: str) -> bool:
    try:
        if not os.path.isfile(path):
            return False
        mtime = os.path.getmtime(path)
        file_date = datetime.fromtimestamp(mtime).date()
        return file_date == datetime.now().date()
    except Exception as e:
        log.error(f"Error checking file modification date: {e!r}")
        return False

def extract_cookies_for_playwright(
    key_path="ai_agents\\tools\\web_tools\\key",
    output_path="ai_agents\\tools\\web_tools\\playwright_cookies.json",
    chrome_profile="Default",
    allow_retry=True
):
    # Step 1: Check if cookies file is present and updated today
    if is_file_modified_today(output_path):
        log.info(f"{output_path} is up-to-date. Skipping extraction.")
        return

    user_profile = os.environ.get("USERPROFILE")
    if not user_profile:
        log.error("USERPROFILE environment variable not found.")
        return

    chrome_cookie_path = os.path.join(
        user_profile,
        fr"AppData\Local\Google\Chrome\User Data\{chrome_profile}\Network\Cookies"
    )

    if not os.path.isfile(key_path):
        log.error(f"Key file not found: {key_path}")
        return

    if not os.path.isfile(chrome_cookie_path):
        log.error(f"Chrome cookie DB not found: {chrome_cookie_path}")
        return

    try:
        with open(key_path, "rb") as f:
            key = binascii.a2b_base64(f.read().strip())
    except Exception as e:
        log.error(f"Failed to read key: {e!r}")
        return

    def decrypt_cookie_v20(encrypted_value: bytes) -> str:
        if not encrypted_value.startswith(b'v20'):
            return ""
        try:
            iv = encrypted_value[3:3+12]
            ciphertext = encrypted_value[3+12:-16]
            tag = encrypted_value[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            return decrypted[32:].decode('utf-8')
        except Exception as e:
            log.error(f"Failed to decrypt cookie: {e!r}")
            return ""

    def chrome_to_playwright(row):
        try:
            value = decrypt_cookie_v20(row[2])
            expires = int(row[4] / 1000000 - 11644473600) if row[4] else -1
            samesite_map = {0: "None", 1: "Lax", 2: "Strict"}
            return {
                "name": row[1],
                "value": value,
                "domain": row[0],
                "path": row[3] if row[3] else "/",
                "expires": expires,
                "httpOnly": bool(row[6]),
                "secure": bool(row[5]),
                "sameSite": samesite_map.get(row[7], "Lax"),
            }
        except Exception as e:
            log.error(f"Failed to convert cookie {row[1]} ({row[0]}): {e!r}")
            return None

    retry_attempted = False
    chrome_restarted = False

    while True:
        try:
            db_uri = f"file:{chrome_cookie_path}?mode=ro"
            con = sqlite3.connect(db_uri, uri=True)
            cur = con.cursor()
            cur.execute("""
                SELECT host_key, name, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite
                FROM cookies
            """)
            rows = cur.fetchall()
            con.close()
            break  # success
        except sqlite3.OperationalError as e:
            log.error(f"Error with cookies DB: {e!r}")
            if "unable to open database file" in str(e) and allow_retry and not retry_attempted:
                log.warning("[ACTION REQUIRED] Enter 'get' to kill all Chrome processes and retry, or 'pass' to skip this step:")
                resp = input("[get/pass]> ").strip().lower()
                if resp == "get":
                    kill_chrome_processes()
                    retry_attempted = True
                    chrome_restarted = True
                    continue
                elif resp == "pass":
                    log.warning("Cookies not saved, skipping.")
                    return
                else:
                    log.warning("Invalid input, try again.")
                    continue
            else:
                log.error("Unable to get cookies, unexpected error.")
                return
        except Exception as e:
            log.error(f"Unexpected error with DB: {e!r}")
            return

    playwright_cookies = []
    for row in rows:
        try:
            if row[2][:3] == b"v20":
                pw_cookie = chrome_to_playwright(row)
                if pw_cookie and pw_cookie["value"]:
                    playwright_cookies.append(pw_cookie)
        except Exception as e:
            log.error(f"Error processing cookie {row[1]} ({row[0]}): {e!r}")

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(playwright_cookies, f, indent=2, ensure_ascii=False)
        log.info(f"Saved {len(playwright_cookies)} cookies for Playwright -> {output_path}")
    except Exception as e:
        log.error(f"Failed to save playwright_cookies.json: {e!r}")

    # Restore Chrome after cookies were extracted (if we killed it)
    if chrome_restarted:
        log.info("Restoring Chrome after cookie extraction...")
        open_chrome()

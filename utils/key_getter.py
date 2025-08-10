import os
import sys
import ctypes
import json
import binascii
from pypsexec.client import Client
from Crypto.Cipher import AES, ChaCha20_Poly1305
from logging_folder import get_logger

log = get_logger(__name__)

def extract_and_save_chrome_key(output_path: str = "ai_agents\\tools\\web_tools\\key"):
    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            log.error(f"Ошибка проверки администратора: {e!r}")
            return False

    try:
        if not is_admin():
            args = " ".join([sys.argv[0]] + sys.argv[1:] + ["--pause-on-exit"])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                args,
                None, 1
            )
            sys.exit()

        user_profile = os.environ['USERPROFILE']
        local_state_path = rf"{user_profile}\AppData\Local\Google\Chrome\User Data\Local State"

        log.info(f"Reading Chrome local state: {local_state_path}")
        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
        except Exception as e:
            log.error(f"Ошибка чтения local state: {e!r}")
            return

        app_bound_encrypted_key = local_state["os_crypt"]["app_bound_encrypted_key"]

        arguments = "-c \"" + """import win32crypt
import binascii
encrypted_key = win32crypt.CryptUnprotectData(binascii.a2b_base64('{}'), None, None, None, 0)
print(binascii.b2a_base64(encrypted_key[1]).decode())
""".replace("\n", ";") + "\""

        c = Client("localhost")
        c.connect()
        try:
            c.create_service()

            assert binascii.a2b_base64(app_bound_encrypted_key)[:4] == b"APPB"
            app_bound_encrypted_key_b64 = binascii.b2a_base64(
                binascii.a2b_base64(app_bound_encrypted_key)[4:]
            ).decode().strip()

            log.info("Decrypting with SYSTEM DPAPI...")
            encrypted_key_b64, stderr, rc = c.run_executable(
                sys.executable,
                arguments=arguments.format(app_bound_encrypted_key_b64),
                use_system_account=True
            )

            log.info("Decrypting with USER DPAPI...")
            decrypted_key_b64, stderr, rc = c.run_executable(
                sys.executable,
                arguments=arguments.format(encrypted_key_b64.decode().strip()),
                use_system_account=False
            )

            decrypted_key = binascii.a2b_base64(decrypted_key_b64)[-61:]

        except Exception as e:
            log.error(f"Ошибка получения ключа через pypsexec: {e!r}")
            return
        finally:
            try:
                c.remove_service()
                c.disconnect()
            except Exception as e:
                log.warning(f"Ошибка disconnect pypsexec: {e!r}")

        try:
            aes_key = bytes.fromhex("B31C6E241AC846728DA9C1FAC4936651CFFB944D143AB816276BCC6DA0284787")
            chacha20_key = bytes.fromhex("E98F37D7F4E1FA433D19304DC2258042090E2D1D7EEA7670D41F738D08729660")

            flag = decrypted_key[0]
            iv = decrypted_key[1:1+12]
            ciphertext = decrypted_key[1+12:1+12+32]
            tag = decrypted_key[1+12+32:]

            if flag == 1:
                cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
            elif flag == 2:
                cipher = ChaCha20_Poly1305.new(key=chacha20_key, nonce=iv)
            else:
                log.error(f"Unsupported flag: {flag}")
                return

            key = cipher.decrypt_and_verify(ciphertext, tag)

            with open(output_path, "wb") as f:
                f.write(binascii.b2a_base64(key))

            log.info(f"[+] Decryption key saved to '{output_path}'")
        except Exception as e:
            log.error(f"Ошибка дешифровки мастер-ключа: {e!r}")


    except Exception as e:
        log.error(f"Critical error in extract_and_save_chrome_key: {e!r}")

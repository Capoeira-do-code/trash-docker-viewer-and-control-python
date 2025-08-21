# core/config.py
import os, json
from cryptography.fernet import Fernet

CONFIG_PATH = os.path.expanduser("~/.helo_wrlod")
PROFILES_FILE = os.path.join(CONFIG_PATH, "profiles.json")
KEY_FILE = os.path.join(CONFIG_PATH, "key.key")


def _load_key():
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(CONFIG_PATH)
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
    else:
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    return key


FERNET = Fernet(_load_key())


def encrypt_password(password: str) -> str:
    return FERNET.encrypt(password.encode()).decode()


def decrypt_password(token: str) -> str:
    return FERNET.decrypt(token.encode()).decode()


def load_profiles():
    if not os.path.exists(PROFILES_FILE):
        return []
    with open(PROFILES_FILE, "r") as f:
        return json.load(f)


def save_profiles(profiles):
    with open(PROFILES_FILE, "w") as f:
        json.dump(profiles, f, indent=2)

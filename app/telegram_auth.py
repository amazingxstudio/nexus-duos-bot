import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from app.config import settings


def verify_telegram_init_data(init_data: str) -> dict | None:
    """
    Verifies Telegram WebApp `initData` per the official algorithm:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app

    Returns the parsed {user, auth_date} dict if valid, otherwise None.
    """
    if not init_data:
        return None

    pairs = parse_qsl(init_data, keep_blank_values=True)
    data = dict(pairs)

    provided_hash = data.pop("hash", None)
    if not provided_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

    secret_key = hmac.new(b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(provided_hash, expected_hash):
        return None

    auth_date = data.get("auth_date")
    if not auth_date or not auth_date.isdigit():
        return None

    age_seconds = int(time.time()) - int(auth_date)
    if age_seconds > settings.TELEGRAM_AUTH_MAX_AGE:
        return None

    user_raw = data.get("user")
    if not user_raw:
        return None

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None

    if not user.get("id") or not user.get("first_name"):
        return None

    return {"user": user, "auth_date": int(auth_date)}

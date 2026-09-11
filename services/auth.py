"""多平台登录：账号密码 / 手机验证码 / 微信 / 钉钉（演示）。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from db.connection import get_connection

# 演示验证码（真实环境应走短信网关，这里固定便于联调）
DEMO_SMS_CODE = "123456"
TOKEN_TTL_HOURS = 24 * 7

PLATFORMS = {
    "password": {
        "id": "password",
        "label": "账号密码",
        "icon": "key",
        "description": "使用用户名和密码登录",
        "fields": ["username", "password"],
    },
    "phone": {
        "id": "phone",
        "label": "手机验证码",
        "icon": "phone",
        "description": "演示验证码固定 123456",
        "fields": ["phone", "code"],
    },
    "wechat": {
        "id": "wechat",
        "label": "微信",
        "icon": "wechat",
        "description": "演示：使用微信授权码登录",
        "fields": ["code"],
    },
    "dingtalk": {
        "id": "dingtalk",
        "label": "钉钉",
        "icon": "dingtalk",
        "description": "演示：使用钉钉授权码登录",
        "fields": ["code"],
    },
}


def hash_password(password: str, salt: str = "meddesk") -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return digest.hex()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash or "")


def list_platforms() -> list[dict]:
    return list(PLATFORMS.values())


def _user_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "phone": row.get("phone"),
        "role": row["role"],
    }


def _issue_token(conn, user_id: int, provider: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(hours=TOKEN_TTL_HOURS)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM auth_tokens WHERE user_id = %s AND provider = %s", (user_id, provider))
        cur.execute(
            """
            INSERT INTO auth_tokens (token, user_id, provider, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (token, user_id, provider, expires),
        )
    return token


def get_user_by_token(token: str | None) -> dict | None:
    if not token:
        return None
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.*, t.token, t.expires_at
                FROM auth_tokens t
                JOIN users u ON u.id = t.user_id
                WHERE t.token = %s AND u.status = 1
                """,
                (token,),
            )
            row = cur.fetchone()
        if not row:
            return None
        if row["expires_at"] and row["expires_at"] < datetime.now():
            return None
        return _user_public(row)
    finally:
        conn.close()


def revoke_token(token: str | None) -> bool:
    if not token:
        return False
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM auth_tokens WHERE token = %s", (token,))
            affected = cur.rowcount
        conn.commit()
        return affected > 0
    finally:
        conn.close()


def _login_with_user(conn, user: dict, provider: str) -> dict:
    token = _issue_token(conn, user["id"], provider)
    conn.commit()
    return {
        "success": True,
        "message": "登录成功",
        "token": token,
        "provider": provider,
        "user": _user_public(user),
    }


def login_password(username: str, password: str) -> dict:
    username = (username or "").strip()
    if not username or not password:
        return {"success": False, "message": "请输入用户名和密码"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE username = %s AND status = 1",
                (username,),
            )
            user = cur.fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return {"success": False, "message": "用户名或密码错误"}
        return _login_with_user(conn, user, "password")
    finally:
        conn.close()


def send_sms_code(phone: str) -> dict:
    phone = (phone or "").strip()
    if not phone or len(phone) < 11:
        return {"success": False, "message": "请输入有效手机号"}
    conn = get_connection()
    try:
        expires = datetime.now() + timedelta(minutes=5)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sms_codes (phone, code, expires_at) VALUES (%s, %s, %s)",
                (phone, DEMO_SMS_CODE, expires),
            )
        conn.commit()
        return {
            "success": True,
            "message": f"验证码已发送（演示环境固定为 {DEMO_SMS_CODE}）",
            "demo_code": DEMO_SMS_CODE,
        }
    finally:
        conn.close()


def login_phone(phone: str, code: str, auto_register: bool = True) -> dict:
    phone = (phone or "").strip()
    code = (code or "").strip()
    if not phone or not code:
        return {"success": False, "message": "请输入手机号和验证码"}
    if code != DEMO_SMS_CODE:
        return {"success": False, "message": "验证码错误（演示环境请用 123456）"}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.* FROM user_identities i
                JOIN users u ON u.id = i.user_id
                WHERE i.provider = 'phone' AND i.external_id = %s AND u.status = 1
                """,
                (phone,),
            )
            user = cur.fetchone()
            if not user:
                cur.execute(
                    "SELECT * FROM users WHERE phone = %s AND status = 1 LIMIT 1",
                    (phone,),
                )
                user = cur.fetchone()
            if not user and auto_register:
                username = f"p{phone[-8:]}"
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, display_name, phone, role)
                    VALUES (%s, '', %s, %s, 'patient')
                    """,
                    (username, f"手机用户{phone[-4:]}", phone),
                )
                uid = cur.lastrowid
                cur.execute(
                    """
                    INSERT INTO user_identities (user_id, provider, external_id)
                    VALUES (%s, 'phone', %s)
                    """,
                    (uid, phone),
                )
                cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
                user = cur.fetchone()
            if not user:
                return {"success": False, "message": "该手机号尚未注册"}
            # 绑定身份（若仅 phone 字段有值）
            cur.execute(
                """
                INSERT IGNORE INTO user_identities (user_id, provider, external_id)
                VALUES (%s, 'phone', %s)
                """,
                (user["id"], phone),
            )
        return _login_with_user(conn, user, "phone")
    finally:
        conn.close()


def _oauth_login(provider: str, code: str, display_name: str) -> dict:
    code = (code or "").strip()
    if not code:
        return {"success": False, "message": f"请输入{PLATFORMS[provider]['label']}授权码"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.* FROM user_identities i
                JOIN users u ON u.id = i.user_id
                WHERE i.provider = %s AND i.external_id = %s AND u.status = 1
                """,
                (provider, code),
            )
            user = cur.fetchone()
            if not user and auto_register_allowed():
                username = f"{provider}_{code[:8]}"
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, display_name, role)
                    VALUES (%s, '', %s, 'patient')
                    """,
                    (username, display_name),
                )
                uid = cur.lastrowid
                cur.execute(
                    """
                    INSERT INTO user_identities (user_id, provider, external_id)
                    VALUES (%s, %s, %s)
                    """,
                    (uid, provider, code),
                )
                cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
                user = cur.fetchone()
            if not user:
                return {"success": False, "message": "授权失败，请重新授权"}
        return _login_with_user(conn, user, provider)
    finally:
        conn.close()


def auto_register_allowed() -> bool:
    return True


def login_wechat(code: str) -> dict:
    return _oauth_login("wechat", code, f"微信用户{code[-4:] or '新'}")


def login_dingtalk(code: str) -> dict:
    return _oauth_login("dingtalk", code, f"钉钉用户{code[-4:] or '新'}")


def register(username: str, password: str, display_name: str = "", phone: str = "") -> dict:
    username = (username or "").strip()
    password = password or ""
    if len(username) < 3:
        return {"success": False, "message": "用户名至少 3 个字符"}
    if len(password) < 6:
        return {"success": False, "message": "密码至少 6 位"}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                return {"success": False, "message": "用户名已存在"}
            cur.execute(
                """
                INSERT INTO users (username, password_hash, display_name, phone, role)
                VALUES (%s, %s, %s, %s, 'patient')
                """,
                (
                    username,
                    hash_password(password),
                    display_name or username,
                    phone or None,
                ),
            )
            uid = cur.lastrowid
            if phone:
                cur.execute(
                    """
                    INSERT IGNORE INTO user_identities (user_id, provider, external_id)
                    VALUES (%s, 'phone', %s)
                    """,
                    (uid, phone),
                )
            cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
            user = cur.fetchone()
        return _login_with_user(conn, user, "password")
    finally:
        conn.close()


def login(platform: str, **kwargs) -> dict:
    platform = (platform or "password").strip().lower()
    if platform == "password":
        return login_password(kwargs.get("username", ""), kwargs.get("password", ""))
    if platform == "phone":
        return login_phone(kwargs.get("phone", ""), kwargs.get("code", ""))
    if platform == "wechat":
        return login_wechat(kwargs.get("code", ""))
    if platform == "dingtalk":
        return login_dingtalk(kwargs.get("code", ""))
    return {"success": False, "message": f"不支持的登录平台: {platform}"}

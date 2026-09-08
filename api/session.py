"""会话管理 — 每个 session 对应一套 MedicalSystem 状态。"""

from __future__ import annotations

import threading
import time
import uuid

from main import MedicalSystem

_SESSION_TTL = 3600 * 4  # 4 小时过期
_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def _sweep():
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s["last_active"] > _SESSION_TTL]
    for sid in expired:
        _sessions.pop(sid, None)


def get_or_create_session(session_id: str | None = None) -> tuple[str, MedicalSystem]:
    with _lock:
        _sweep()
        if session_id and session_id in _sessions:
            _sessions[session_id]["last_active"] = time.time()
            return session_id, _sessions[session_id]["system"]

        sid = session_id or uuid.uuid4().hex[:12]
        system = MedicalSystem()
        _sessions[sid] = {"system": system, "last_active": time.time()}
        return sid, system


def get_session(session_id: str) -> MedicalSystem | None:
    with _lock:
        _sweep()
        entry = _sessions.get(session_id)
        if not entry:
            return None
        entry["last_active"] = time.time()
        return entry["system"]


def reset_session(session_id: str) -> bool:
    system = get_session(session_id)
    if not system:
        return False
    system.reset()
    return True


def delete_session(session_id: str) -> bool:
    with _lock:
        return _sessions.pop(session_id, None) is not None


def session_count() -> int:
    with _lock:
        _sweep()
        return len(_sessions)

"""排队叫号工具 - MySQL 持久化。"""

from __future__ import annotations

from datetime import datetime

from db.connection import get_connection
from db.schema import bootstrap

AVG_SERVICE_TIME = 8

_bootstrapped = False


def _ensure_db() -> None:
    global _bootstrapped
    if not _bootstrapped:
        bootstrap()
        _bootstrapped = True


def _dept_and_queue(conn, department: str) -> tuple[int, dict] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM departments WHERE name = %s", (department,))
        dept = cur.fetchone()
        if not dept:
            return None
        dept_id = dept["id"]
        cur.execute(
            """
            SELECT current_number, counter
            FROM queue_states
            WHERE department_id = %s
            FOR UPDATE
            """,
            (dept_id,),
        )
        state = cur.fetchone()
        if not state:
            cur.execute(
                "INSERT INTO queue_states (department_id, current_number, counter) VALUES (%s, 0, 0)",
                (dept_id,),
            )
            state = {"current_number": 0, "counter": 0}
        return dept_id, state


def take_number(department: str, patient_name: str, user_id: int | None = None) -> dict:
    _ensure_db()
    conn = get_connection()
    try:
        locked = _dept_and_queue(conn, department)
        if not locked:
            return {"success": False, "message": f"未找到科室「{department}」。"}
        dept_id, state = locked

        number = int(state["counter"]) + 1
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO queue_tickets
                    (department_id, queue_number, patient_name, status, user_id)
                VALUES (%s, %s, %s, 'waiting', %s)
                """,
                (dept_id, number, patient_name, user_id),
            )
            cur.execute(
                "UPDATE queue_states SET counter = %s, current_number = %s WHERE department_id = %s",
                (number, state["current_number"], dept_id),
            )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM queue_tickets
                WHERE department_id = %s AND status = 'waiting' AND queue_number < %s
                """,
                (dept_id, number),
            )
            ahead = cur.fetchone()["c"]

        estimated_minutes = ahead * AVG_SERVICE_TIME
        return {
            "success": True,
            "queue_number": number,
            "department": department,
            "patient_name": patient_name,
            "ahead_count": ahead,
            "estimated_wait": (
                f"约{estimated_minutes}分钟" if estimated_minutes > 0 else "即将到您"
            ),
        }
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"success": False, "message": f"取号失败：{e}"}
    finally:
        conn.close()


def query_queue(department: str, queue_number: int = None) -> dict:
    _ensure_db()
    conn = get_connection()
    try:
        locked = _dept_and_queue(conn, department)
        if not locked:
            return {"success": False, "message": f"未找到科室「{department}」。"}
        dept_id, state = locked
        current = int(state["current_number"])

        if queue_number:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT queue_number, status FROM queue_tickets
                    WHERE department_id = %s AND queue_number = %s
                    """,
                    (dept_id, queue_number),
                )
                ticket = cur.fetchone()

            if not ticket:
                if queue_number <= current:
                    return {
                        "success": True,
                        "message": f"号码 {queue_number} 已经就诊完毕。",
                    }
                return {"success": False, "message": f"未找到号码 {queue_number}。"}

            if ticket["status"] in ("done", "serving"):
                return {
                    "success": True,
                    "message": f"号码 {queue_number} 已经就诊完毕。",
                }
            if ticket["status"] == "cancelled":
                return {
                    "success": False,
                    "message": f"号码 {queue_number} 已取消排队。",
                }

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS c FROM queue_tickets
                    WHERE department_id = %s AND status = 'waiting' AND queue_number < %s
                    """,
                    (dept_id, queue_number),
                )
                ahead = cur.fetchone()["c"]

            return {
                "success": True,
                "queue_number": queue_number,
                "ahead_count": ahead,
                "estimated_wait": f"约{ahead * AVG_SERVICE_TIME}分钟",
                "current_serving": current,
            }

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM queue_tickets
                WHERE department_id = %s AND status = 'waiting'
                """,
                (dept_id,),
            )
            waiting_count = cur.fetchone()["c"]
            cur.execute(
                """
                SELECT queue_number FROM queue_tickets
                WHERE department_id = %s AND status = 'waiting'
                ORDER BY queue_number ASC LIMIT 1
                """,
                (dept_id,),
            )
            nxt = cur.fetchone()

        return {
            "success": True,
            "department": department,
            "current_serving": current,
            "waiting_count": waiting_count,
            "next_number": nxt["queue_number"] if nxt else None,
        }
    finally:
        conn.close()


def call_next(department: str) -> dict:
    _ensure_db()
    conn = get_connection()
    try:
        locked = _dept_and_queue(conn, department)
        if not locked:
            return {"success": False, "message": f"未找到科室「{department}」。"}
        dept_id, state = locked

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, queue_number, patient_name
                FROM queue_tickets
                WHERE department_id = %s AND status = 'waiting'
                ORDER BY queue_number ASC LIMIT 1
                FOR UPDATE
                """,
                (dept_id,),
            )
            nxt = cur.fetchone()
            if not nxt:
                return {
                    "success": False,
                    "message": f"科室「{department}」当前没有等待的患者。",
                }

            # 原「当前号」标为完成
            cur.execute(
                """
                UPDATE queue_tickets
                SET status = 'done'
                WHERE department_id = %s AND status = 'serving'
                """,
                (dept_id,),
            )
            cur.execute(
                """
                UPDATE queue_tickets
                SET status = 'serving', called_at = %s
                WHERE id = %s
                """,
                (datetime.now(), nxt["id"]),
            )
            cur.execute(
                "UPDATE queue_states SET current_number = %s WHERE department_id = %s",
                (nxt["queue_number"], dept_id),
            )
        conn.commit()

        return {
            "success": True,
            "called_number": nxt["queue_number"],
            "patient_name": nxt["patient_name"],
            "department": department,
            "message": (
                f"请 {nxt['patient_name']}（{nxt['queue_number']}号）"
                f"到{department}诊室就诊。"
            ),
        }
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"success": False, "message": f"叫号失败：{e}"}
    finally:
        conn.close()


def cancel_queue(department: str, queue_number: int) -> dict:
    _ensure_db()
    conn = get_connection()
    try:
        locked = _dept_and_queue(conn, department)
        if not locked:
            return {"success": False, "message": f"未找到科室「{department}」。"}
        dept_id, state = locked

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status FROM queue_tickets
                WHERE department_id = %s AND queue_number = %s
                """,
                (dept_id, queue_number),
            )
            ticket = cur.fetchone()
            if not ticket:
                if queue_number <= int(state["current_number"]):
                    return {
                        "success": False,
                        "message": f"号码 {queue_number} 已就诊完毕，无法取消。",
                    }
                return {"success": False, "message": f"未找到号码 {queue_number}。"}
            if ticket["status"] != "waiting":
                return {
                    "success": False,
                    "message": f"号码 {queue_number} 已就诊完毕，无法取消。",
                }
            cur.execute(
                "UPDATE queue_tickets SET status = 'cancelled' WHERE id = %s",
                (ticket["id"],),
            )
        conn.commit()
        return {"success": True, "message": f"号码 {queue_number} 已取消排队。"}
    finally:
        conn.close()


def execute(action: str, params: dict) -> dict:
    if action == "take_number":
        return take_number(
            params.get("department", ""),
            params.get("patient_name", ""),
            params.get("user_id"),
        )
    elif action == "query_queue":
        return query_queue(params.get("department", ""), params.get("queue_number"))
    elif action == "call_next":
        return call_next(params.get("department", ""))
    elif action == "cancel_queue":
        return cancel_queue(params.get("department", ""), params.get("queue_number", 0))
    else:
        return {"success": False, "message": f"未知操作: {action}"}

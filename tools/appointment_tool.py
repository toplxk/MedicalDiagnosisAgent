"""预约挂号工具 - MySQL 持久化（科室/医生/排班/预约）。"""

from __future__ import annotations

import random
from datetime import datetime

from db.connection import get_connection
from db.schema import bootstrap

_bootstrapped = False


def _ensure_db() -> None:
    global _bootstrapped
    if not _bootstrapped:
        bootstrap()
        _bootstrapped = True


def _dept_id(conn, department: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM departments WHERE name = %s", (department,))
        row = cur.fetchone()
        return row["id"] if row else None


def _doctor_row(conn, department_id: int, doctor_name: str | None) -> dict | None:
    with conn.cursor() as cur:
        if doctor_name:
            cur.execute(
                """
                SELECT id, name, title, specialty
                FROM doctors
                WHERE department_id = %s AND name = %s
                """,
                (department_id, doctor_name),
            )
            return cur.fetchone()
        cur.execute(
            """
            SELECT id, name, title, specialty
            FROM doctors
            WHERE department_id = %s
            """,
            (department_id,),
        )
        rows = cur.fetchall()
        return random.choice(rows) if rows else None


def _ensure_schedule(conn, doctor_id: int, date: str) -> list[str]:
    """确保医生在指定日期有排班记录，返回可用时段。"""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT period, available_slots
            FROM doctor_schedules
            WHERE doctor_id = %s AND schedule_date = %s
            """,
            (doctor_id, date),
        )
        rows = cur.fetchall()
        if rows:
            return [r["period"] for r in rows if r["available_slots"] > 0] or [
                r["period"] for r in rows
            ]

    # 首次查询该日期：生成并落库
    periods: list[str] = []
    if random.random() > 0.3:
        periods.append("上午")
    if random.random() > 0.3:
        periods.append("下午")
    if not periods:
        periods = ["上午"]

    with conn.cursor() as cur:
        for period in periods:
            cur.execute(
                """
                INSERT IGNORE INTO doctor_schedules
                    (doctor_id, schedule_date, period, available_slots)
                VALUES (%s, %s, %s, %s)
                """,
                (doctor_id, date, period, random.randint(3, 15)),
            )
    conn.commit()
    return periods


def query_schedule(department: str, date: str = None) -> dict:
    _ensure_db()
    date = date or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        dept_id = _dept_id(conn, department)
        if not dept_id:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM departments ORDER BY id")
                available = [r["name"] for r in cur.fetchall()]
            return {
                "success": False,
                "message": f"未找到科室「{department}」，可用科室：{', '.join(available)}",
            }

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, title, specialty
                FROM doctors
                WHERE department_id = %s
                ORDER BY id
                """,
                (dept_id,),
            )
            doctors = cur.fetchall()

        schedule_info = []
        for doc in doctors:
            periods = _ensure_schedule(conn, doc["id"], date)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT period, available_slots
                    FROM doctor_schedules
                    WHERE doctor_id = %s AND schedule_date = %s
                    """,
                    (doc["id"], date),
                )
                slot_rows = {r["period"]: r["available_slots"] for r in cur.fetchall()}
            schedule_info.append(
                {
                    "doctor": doc["name"],
                    "title": doc["title"],
                    "specialty": doc["specialty"],
                    "date": date,
                    "periods": periods,
                    "available_slots": max(slot_rows.values()) if slot_rows else 0,
                }
            )

        return {
            "success": True,
            "department": department,
            "date": date,
            "schedule": schedule_info,
        }
    finally:
        conn.close()


def _next_appointment_id(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM appointment_seq FOR UPDATE")
        row = cur.fetchone()
        next_id = (row["id"] if row else 1000) + 1
        if row:
            cur.execute("UPDATE appointment_seq SET id = %s", (next_id,))
        else:
            cur.execute("INSERT INTO appointment_seq (id) VALUES (%s)", (next_id,))
    return f"APT{next_id}"


def create_appointment(
    department: str,
    doctor: str,
    date: str,
    period: str,
    patient_name: str,
    phone: str,
    user_id: int | None = None,
) -> dict:
    _ensure_db()
    if not all([department, date, period, patient_name, phone]):
        return {"success": False, "message": "预约信息不完整，请提供所有必要信息。"}

    conn = get_connection()
    try:
        dept_id = _dept_id(conn, department)
        if not dept_id:
            return {"success": False, "message": f"未找到科室「{department}」。"}

        doc = _doctor_row(conn, dept_id, doctor or None)
        if not doc:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name FROM doctors WHERE department_id = %s ORDER BY id",
                    (dept_id,),
                )
                names = [r["name"] for r in cur.fetchall()]
            if doctor:
                return {
                    "success": False,
                    "message": f"科室「{department}」没有医生「{doctor}」，可用医生：{', '.join(names)}",
                }
            return {"success": False, "message": f"科室「{department}」暂无医生排班。"}

        _ensure_schedule(conn, doc["id"], date)

        appointment_id = _next_appointment_id(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO appointments
                    (appointment_id, department_id, doctor_id, schedule_date,
                     period, patient_name, phone, status, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, '已预约', %s)
                """,
                (
                    appointment_id,
                    dept_id,
                    doc["id"],
                    date,
                    period,
                    patient_name,
                    phone,
                    user_id,
                ),
            )
            # 扣减可约号源
            cur.execute(
                """
                UPDATE doctor_schedules
                SET available_slots = GREATEST(available_slots - 1, 0)
                WHERE doctor_id = %s AND schedule_date = %s AND period = %s
                """,
                (doc["id"], date, period),
            )
        conn.commit()

        detail = {
            "id": appointment_id,
            "department": department,
            "doctor": doc["name"],
            "date": date,
            "period": period,
            "patient_name": patient_name,
            "phone": phone,
            "status": "已预约",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return {
            "success": True,
            "appointment_id": appointment_id,
            "message": f"预约成功！您的预约编号为 {appointment_id}",
            "detail": detail,
        }
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        return {"success": False, "message": f"预约失败：{e}"}
    finally:
        conn.close()


def cancel_appointment(appointment_id: str) -> dict:
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM appointments WHERE appointment_id = %s",
                (appointment_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"success": False, "message": f"未找到预约编号 {appointment_id}。"}
            if row["status"] == "已取消":
                return {"success": False, "message": "该预约已经被取消。"}
            cur.execute(
                "UPDATE appointments SET status = '已取消' WHERE appointment_id = %s",
                (appointment_id,),
            )
        conn.commit()
        return {"success": True, "message": f"预约 {appointment_id} 已成功取消。"}
    finally:
        conn.close()


def query_appointment(appointment_id: str) -> dict:
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.appointment_id AS id, d.name AS department, doc.name AS doctor,
                       a.schedule_date AS date, a.period, a.patient_name, a.phone,
                       a.status, a.created_at
                FROM appointments a
                JOIN departments d ON d.id = a.department_id
                JOIN doctors doc ON doc.id = a.doctor_id
                WHERE a.appointment_id = %s
                """,
                (appointment_id,),
            )
            row = cur.fetchone()
        if not row:
            return {"success": False, "message": f"未找到预约编号 {appointment_id}。"}
        # 统一 date 格式
        if hasattr(row.get("date"), "strftime"):
            row["date"] = row["date"].strftime("%Y-%m-%d")
        if hasattr(row.get("created_at"), "strftime"):
            row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M")
        return {"success": True, "detail": row}
    finally:
        conn.close()


def list_departments() -> list[str]:
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM departments ORDER BY id")
            return [r["name"] for r in cur.fetchall()]
    finally:
        conn.close()


def list_doctors(department: str | None = None) -> list[dict]:
    _ensure_db()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if department:
                cur.execute(
                    """
                    SELECT doc.id, d.name AS department, doc.name, doc.title, doc.specialty
                    FROM doctors doc
                    JOIN departments d ON d.id = doc.department_id
                    WHERE d.name = %s
                    ORDER BY doc.id
                    """,
                    (department,),
                )
            else:
                cur.execute(
                    """
                    SELECT doc.id, d.name AS department, doc.name, doc.title, doc.specialty
                    FROM doctors doc
                    JOIN departments d ON d.id = doc.department_id
                    ORDER BY d.id, doc.id
                    """
                )
            return cur.fetchall()
    finally:
        conn.close()


def execute(action: str, params: dict) -> dict:
    if action == "query_schedule":
        return query_schedule(params.get("department", ""), params.get("date"))
    elif action == "create_appointment":
        return create_appointment(
            params.get("department", ""),
            params.get("doctor", ""),
            params.get("date", ""),
            params.get("period", ""),
            params.get("patient_name", ""),
            params.get("phone", ""),
            params.get("user_id"),
        )
    elif action == "cancel_appointment":
        return cancel_appointment(params.get("appointment_id", ""))
    elif action == "query_appointment":
        return query_appointment(params.get("appointment_id", ""))
    elif action == "list_departments":
        return {"success": True, "departments": list_departments()}
    elif action == "list_doctors":
        return {"success": True, "doctors": list_doctors(params.get("department"))}
    else:
        return {"success": False, "message": f"未知操作: {action}"}

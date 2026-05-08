"""预约挂号工具 - 模拟数据库管理预约记录"""

import random
from datetime import datetime, timedelta

# 模拟的医生排班数据
_doctor_schedule = {
    "内科": [
        {"name": "张建国", "title": "主任医师", "specialty": "心血管、高血压"},
        {"name": "李明华", "title": "副主任医师", "specialty": "呼吸系统疾病"},
        {"name": "王芳", "title": "主治医师", "specialty": "消化系统疾病"},
    ],
    "外科": [
        {"name": "刘强", "title": "主任医师", "specialty": "普通外科"},
        {"name": "陈伟", "title": "副主任医师", "specialty": "骨科"},
    ],
    "儿科": [
        {"name": "赵敏", "title": "主任医师", "specialty": "小儿呼吸"},
        {"name": "孙丽", "title": "副主任医师", "specialty": "小儿消化"},
    ],
    "妇产科": [
        {"name": "周洁", "title": "主任医师", "specialty": "妇科肿瘤"},
        {"name": "吴婷", "title": "副主任医师", "specialty": "产科"},
    ],
    "眼科": [
        {"name": "黄明", "title": "主任医师", "specialty": "白内障、青光眼"},
    ],
    "耳鼻喉科": [
        {"name": "郑伟", "title": "副主任医师", "specialty": "鼻炎、中耳炎"},
    ],
    "皮肤科": [
        {"name": "林小红", "title": "主任医师", "specialty": "湿疹、银屑病"},
    ],
    "中医科": [
        {"name": "马永健", "title": "主任医师", "specialty": "中医内科调理"},
    ],
    "骨科": [
        {"name": "杨志刚", "title": "主任医师", "specialty": "脊柱外科"},
        {"name": "陈伟", "title": "副主任医师", "specialty": "关节外科"},
    ],
    "神经内科": [
        {"name": "韩冰", "title": "主任医师", "specialty": "脑血管疾病"},
    ],
    "口腔科": [
        {"name": "许洁", "title": "主治医师", "specialty": "口腔修复"},
    ],
    "精神科": [
        {"name": "何志强", "title": "主任医师", "specialty": "抑郁症、焦虑症"},
    ],
}

# 模拟的预约记录存储
_appointments: dict[str, dict] = {}
_id_counter = 1000


def query_schedule(department: str, date: str = None) -> dict:
    """查询科室排班信息。

    Args:
        department: 科室名称
        date: 查询日期（可选）

    Returns:
        {"success": bool, "data": 排班信息或错误信息}
    """
    doctors = _doctor_schedule.get(department)
    if not doctors:
        available = list(_doctor_schedule.keys())
        return {
            "success": False,
            "message": f"未找到科室「{department}」，可用科室：{', '.join(available)}",
        }

    date = date or datetime.now().strftime("%Y-%m-%d")
    schedule_info = []
    for doc in doctors:
        # 模拟排班：随机上午/下午
        periods = []
        if random.random() > 0.3:
            periods.append("上午")
        if random.random() > 0.3:
            periods.append("下午")
        if not periods:
            periods = ["上午"]
        schedule_info.append({
            "doctor": doc["name"],
            "title": doc["title"],
            "specialty": doc["specialty"],
            "date": date,
            "periods": periods,
            "available_slots": random.randint(3, 15),
        })

    return {
        "success": True,
        "department": department,
        "date": date,
        "schedule": schedule_info,
    }


def create_appointment(department: str, doctor: str, date: str, period: str,
                       patient_name: str, phone: str) -> dict:
    """创建预约。

    Returns:
        {"success": bool, "appointment_id": str, "message": str}
    """
    global _id_counter

    if not all([department, date, period, patient_name, phone]):
        return {"success": False, "message": "预约信息不完整，请提供所有必要信息。"}

    # 验证科室和医生
    doctors = _doctor_schedule.get(department)
    if not doctors:
        return {"success": False, "message": f"未找到科室「{department}」。"}

    if doctor:
        doc_names = [d["name"] for d in doctors]
        if doctor not in doc_names:
            return {
                "success": False,
                "message": f"科室「{department}」没有医生「{doctor}」，可用医生：{', '.join(doc_names)}",
            }
    else:
        doctor = random.choice(doctors)["name"]

    _id_counter += 1
    appointment_id = f"APT{_id_counter}"
    _appointments[appointment_id] = {
        "id": appointment_id,
        "department": department,
        "doctor": doctor,
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
        "detail": _appointments[appointment_id],
    }


def cancel_appointment(appointment_id: str) -> dict:
    """取消预约。"""
    if appointment_id not in _appointments:
        return {"success": False, "message": f"未找到预约编号 {appointment_id}。"}

    appt = _appointments[appointment_id]
    if appt["status"] == "已取消":
        return {"success": False, "message": "该预约已经被取消。"}

    appt["status"] = "已取消"
    return {"success": True, "message": f"预约 {appointment_id} 已成功取消。"}


def query_appointment(appointment_id: str) -> dict:
    """查询预约信息。"""
    if appointment_id not in _appointments:
        return {"success": False, "message": f"未找到预约编号 {appointment_id}。"}

    return {"success": True, "detail": _appointments[appointment_id]}


def list_departments() -> list[str]:
    """列出所有可用科室。"""
    return list(_doctor_schedule.keys())


def execute(action: str, params: dict) -> dict:
    """工具统一入口。"""
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
        )
    elif action == "cancel_appointment":
        return cancel_appointment(params.get("appointment_id", ""))
    elif action == "query_appointment":
        return query_appointment(params.get("appointment_id", ""))
    elif action == "list_departments":
        return {"success": True, "departments": list_departments()}
    else:
        return {"success": False, "message": f"未知操作: {action}"}

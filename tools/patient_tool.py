"""患者信息工具 - 模拟患者档案管理"""

from datetime import datetime

# 模拟患者数据存储
_patients: dict[str, dict] = {}


def create_patient(name: str, gender: str = None, age: int = None, phone: str = None,
                   id_card: str = None, allergies: str = None, medical_history: str = None) -> dict:
    """创建患者档案。"""
    patient_id = f"P{len(_patients) + 1001}"
    _patients[patient_id] = {
        "id": patient_id,
        "name": name,
        "gender": gender,
        "age": age,
        "phone": phone,
        "id_card": id_card,
        "allergies": allergies or "无",
        "medical_history": medical_history or "无",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "visit_count": 0,
    }
    return {"success": True, "patient_id": patient_id, "message": f"患者档案创建成功，编号 {patient_id}"}


def query_patient(patient_id: str = None, name: str = None) -> dict:
    """查询患者信息。"""
    if patient_id and patient_id in _patients:
        return {"success": True, "patient": _patients[patient_id]}

    if name:
        found = [p for p in _patients.values() if p["name"] == name]
        if found:
            return {"success": True, "patients": found}
        return {"success": False, "message": f"未找到患者「{name}」。"}

    return {"success": False, "message": "请提供患者编号或姓名。"}


def update_patient(patient_id: str, **kwargs) -> dict:
    """更新患者信息。"""
    if patient_id not in _patients:
        return {"success": False, "message": f"未找到患者编号 {patient_id}。"}

    patient = _patients[patient_id]
    for key, value in kwargs.items():
        if key in patient and value is not None:
            patient[key] = value

    return {"success": True, "message": "患者信息已更新。", "patient": patient}


def add_visit_record(patient_id: str, diagnosis: str, prescription: str = None,
                     doctor: str = None, notes: str = None) -> dict:
    """添加就诊记录。"""
    if patient_id not in _patients:
        return {"success": False, "message": f"未找到患者编号 {patient_id}。"}

    patient = _patients[patient_id]
    patient["visit_count"] += 1

    if "visit_records" not in patient:
        patient["visit_records"] = []

    patient["visit_records"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "diagnosis": diagnosis,
        "prescription": prescription,
        "doctor": doctor,
        "notes": notes,
    })

    return {"success": True, "message": "就诊记录已添加。"}


def execute(action: str, params: dict) -> dict:
    """工具统一入口。"""
    if action == "create_patient":
        return create_patient(
            params.get("name", ""),
            params.get("gender"),
            params.get("age"),
            params.get("phone"),
            params.get("id_card"),
            params.get("allergies"),
            params.get("medical_history"),
        )
    elif action == "query_patient":
        return query_patient(params.get("patient_id"), params.get("name"))
    elif action == "update_patient":
        return update_patient(params.get("patient_id", ""), **{k: v for k, v in params.items() if k != "patient_id"})
    elif action == "add_visit_record":
        return add_visit_record(
            params.get("patient_id", ""),
            params.get("diagnosis", ""),
            params.get("prescription"),
            params.get("doctor"),
            params.get("notes"),
        )
    else:
        return {"success": False, "message": f"未知操作: {action}"}

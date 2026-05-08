"""排队叫号工具 - 模拟排队系统"""

from datetime import datetime

# 科室队列数据：{department: {"current": 当前叫号, "waiting": [{"number": N, "name": "...", "time": "..."}], "counter": 最大已取号码}}
_queues: dict[str, dict] = {}

# 每位患者平均就诊时间（分钟）
AVG_SERVICE_TIME = 8


def _init_queue(department: str):
    """初始化科室队列。"""
    if department not in _queues:
        _queues[department] = {"current": 0, "waiting": [], "counter": 0}


def take_number(department: str, patient_name: str) -> dict:
    """取号排队。

    Returns:
        {"success": bool, "queue_number": int, "ahead_count": int, "estimated_wait": str}
    """
    _init_queue(department)
    queue = _queues[department]

    queue["counter"] += 1
    number = queue["counter"]
    queue["waiting"].append({
        "number": number,
        "name": patient_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

    ahead_count = len(queue["waiting"]) - 1
    estimated_minutes = ahead_count * AVG_SERVICE_TIME

    return {
        "success": True,
        "queue_number": number,
        "department": department,
        "patient_name": patient_name,
        "ahead_count": ahead_count,
        "estimated_wait": f"约{estimated_minutes}分钟" if estimated_minutes > 0 <= 1 else "即将到您",
    }


def query_queue(department: str, queue_number: int = None) -> dict:
    """查询排队状态。"""
    _init_queue(department)
    queue = _queues[department]

    if queue_number:
        # 查询特定号码
        found = False
        position = -1
        for i, item in enumerate(queue["waiting"]):
            if item["number"] == queue_number:
                found = True
                position = i
                break

        if not found:
            if queue_number <= queue["current"]:
                return {"success": True, "message": f"号码 {queue_number} 已经就诊完毕。"}
            return {"success": False, "message": f"未找到号码 {queue_number}。"}

        ahead = position
        return {
            "success": True,
            "queue_number": queue_number,
            "ahead_count": ahead,
            "estimated_wait": f"约{ahead * AVG_SERVICE_TIME}分钟",
            "current_serving": queue["current"],
        }
    else:
        # 查询整体状态
        return {
            "success": True,
            "department": department,
            "current_serving": queue["current"],
            "waiting_count": len(queue["waiting"]),
            "next_number": queue["waiting"][0]["number"] if queue["waiting"] else None,
        }


def call_next(department: str) -> dict:
    """叫下一个号。"""
    _init_queue(department)
    queue = _queues[department]

    if not queue["waiting"]:
        return {"success": False, "message": f"科室「{department}」当前没有等待的患者。"}

    next_patient = queue["waiting"].pop(0)
    queue["current"] = next_patient["number"]

    return {
        "success": True,
        "called_number": next_patient["number"],
        "patient_name": next_patient["name"],
        "department": department,
        "message": f"请 {next_patient['name']}（{next_patient['number']}号）到{department}诊室就诊。",
    }


def cancel_queue(department: str, queue_number: int) -> dict:
    """取消排队。"""
    _init_queue(department)
    queue = _queues[department]

    for i, item in enumerate(queue["waiting"]):
        if item["number"] == queue_number:
            queue["waiting"].pop(i)
            return {"success": True, "message": f"号码 {queue_number} 已取消排队。"}

    if queue_number <= queue["current"]:
        return {"success": False, "message": f"号码 {queue_number} 已就诊完毕，无法取消。"}

    return {"success": False, "message": f"未找到号码 {queue_number}。"}


def execute(action: str, params: dict) -> dict:
    """工具统一入口。"""
    if action == "take_number":
        return take_number(params.get("department", ""), params.get("patient_name", ""))
    elif action == "query_queue":
        return query_queue(params.get("department", ""), params.get("queue_number"))
    elif action == "call_next":
        return call_next(params.get("department", ""))
    elif action == "cancel_queue":
        return cancel_queue(params.get("department", ""), params.get("queue_number", 0))
    else:
        return {"success": False, "message": f"未知操作: {action}"}

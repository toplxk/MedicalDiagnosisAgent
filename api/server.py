"""智能医疗诊断多 Agent 系统 — FastAPI 服务入口。

启动：
    python -m api.server
    或
    uvicorn api.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import session as session_store
from api.schemas import (
    ApiEnvelope,
    AppointmentIdRequest,
    CallNextRequest,
    CancelQueueRequest,
    ChatRequest,
    ChatResponse,
    CreateAppointmentRequest,
    LoginRequest,
    QueueQueryRequest,
    RegisterRequest,
    ScheduleQuery,
    SessionActionResponse,
    SmsRequest,
    TakeNumberRequest,
)
from config import MEDICAL_DOCS_DIR
from main import MedicalSystem
from rag.vector_store import get_collection_count
from services import auth as auth_service
from tools import appointment_tool, patient_tool, queue_tool, symptom_tool

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

_rag_ready = False
_rag_error: str | None = None
_rag_lock = threading.Lock()


def _init_rag_once():
    """启动时后台初始化 RAG 知识库。"""
    global _rag_ready, _rag_error
    with _rag_lock:
        if _rag_ready:
            return
        try:
            system = MedicalSystem()
            system.init_rag()
            _rag_ready = True
            _rag_error = None
        except Exception as e:  # noqa: BLE001
            _rag_error = str(e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        from db.schema import bootstrap

        bootstrap()
    except Exception as e:  # noqa: BLE001
        print(f"[DB] 初始化失败: {e}")
    thread = threading.Thread(target=_init_rag_once, daemon=True)
    thread.start()
    yield


app = FastAPI(
    title="智能医疗诊断多 Agent 系统",
    description="预约挂号 / 排队叫号 / 医疗咨询 / 症状诊断",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _envelope(result: dict[str, Any]) -> ApiEnvelope:
    success = bool(result.get("success", False))
    message = result.get("message", "")
    data = {k: v for k, v in result.items() if k not in ("success", "message")}
    return ApiEnvelope(success=success, message=message, data=data)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def current_user(authorization: str | None = Header(None)) -> dict | None:
    return auth_service.get_user_by_token(_bearer_token(authorization))


# ── 登录 / 多平台 ────────────────────────────────────────────


@app.get("/api/auth/platforms")
def auth_platforms():
    return {"success": True, "platforms": auth_service.list_platforms()}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    result = auth_service.login(
        req.platform,
        username=req.username,
        password=req.password,
        phone=req.phone,
        code=req.code,
    )
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("message", "登录失败"))
    return result


@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    result = auth_service.register(req.username, req.password, req.display_name, req.phone)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "注册失败"))
    return result


@app.post("/api/auth/sms")
def auth_sms(req: SmsRequest):
    return auth_service.send_sms_code(req.phone)


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(None)):
    user = auth_service.get_user_by_token(_bearer_token(authorization))
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return {"success": True, "user": user}


@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = Header(None)):
    token = _bearer_token(authorization)
    ok = auth_service.revoke_token(token)
    return {"success": True, "message": "已退出登录" if ok else "会话不存在"}


# ── 健康 / 状态 ──────────────────────────────────────────────


@app.get("/api/health")
def health():
    try:
        count = get_collection_count()
    except Exception as e:  # noqa: BLE001
        count = -1
        rag_msg = f"向量库不可用: {e}"
    else:
        rag_msg = "就绪" if count > 0 else "知识库为空（可触发 /api/rag/init）"

    return {
        "status": "ok",
        "llm_model": "configured",
        "rag": {
            "ready": _rag_ready and count > 0,
            "doc_count": count,
            "message": _rag_error or rag_msg,
            "initializing": not _rag_ready and _rag_error is None,
        },
        "sessions": session_store.session_count(),
    }


@app.post("/api/rag/init")
def init_rag():
    threading.Thread(target=_init_rag_once, daemon=True).start()
    return {"ok": True, "message": "RAG 初始化已触发（后台执行）"}


# ── 对话 ─────────────────────────────────────────────────────


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    sid, system = session_store.get_or_create_session(req.session_id)
    try:
        result = system.process_message(req.message, echo=False)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"处理消息失败: {e}") from e

    return ChatResponse(
        session_id=sid,
        reply=result.get("reply", ""),
        intent=result.get("intent", "chitchat"),
        confidence=float(result.get("confidence") or 0),
        agent=result.get("agent"),
        needs_clarification=bool(result.get("needs_clarification")),
        extracted_info=result.get("extracted_info") or {},
        collected_info=result.get("collected_info"),
        round_count=result.get("round_count"),
    )


@app.post("/api/session/reset", response_model=SessionActionResponse)
def reset_session(req: ChatRequest):
    sid = req.session_id
    if not sid:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    ok = session_store.reset_session(sid)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return SessionActionResponse(session_id=sid, ok=True, message="对话已重置")


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    ok = session_store.delete_session(session_id)
    return {"ok": ok}


# ── 排班 / 预约 ──────────────────────────────────────────────


@app.get("/api/departments", response_model=ApiEnvelope)
def list_departments():
    return _envelope({"success": True, "departments": appointment_tool.list_departments()})


@app.get("/api/doctors", response_model=ApiEnvelope)
def list_doctors(department: str | None = Query(None)):
    return _envelope({"success": True, "doctors": appointment_tool.list_doctors(department)})


@app.post("/api/schedule", response_model=ApiEnvelope)
def query_schedule(req: ScheduleQuery):
    return _envelope(appointment_tool.query_schedule(req.department, req.date))


@app.post("/api/appointments", response_model=ApiEnvelope)
def create_appointment(req: CreateAppointmentRequest, authorization: str | None = Header(None)):
    user = auth_service.get_user_by_token(_bearer_token(authorization))
    result = appointment_tool.create_appointment(
        req.department,
        req.doctor,
        req.date,
        req.period,
        req.patient_name,
        req.phone,
        user_id=user["id"] if user else None,
    )
    return _envelope(result)


@app.post("/api/appointments/query", response_model=ApiEnvelope)
def query_appointment(req: AppointmentIdRequest):
    return _envelope(appointment_tool.query_appointment(req.appointment_id))


@app.post("/api/appointments/cancel", response_model=ApiEnvelope)
def cancel_appointment(req: AppointmentIdRequest):
    return _envelope(appointment_tool.cancel_appointment(req.appointment_id))


# ── 排队 ─────────────────────────────────────────────────────


@app.post("/api/queue/take", response_model=ApiEnvelope)
def take_number(req: TakeNumberRequest, authorization: str | None = Header(None)):
    user = auth_service.get_user_by_token(_bearer_token(authorization))
    result = queue_tool.take_number(
        req.department,
        req.patient_name,
        user_id=user["id"] if user else None,
    )
    return _envelope(result)


@app.post("/api/queue/query", response_model=ApiEnvelope)
def query_queue(req: QueueQueryRequest):
    return _envelope(queue_tool.query_queue(req.department, req.queue_number))


@app.post("/api/queue/call-next", response_model=ApiEnvelope)
def call_next(req: CallNextRequest):
    return _envelope(queue_tool.call_next(req.department))


@app.post("/api/queue/cancel", response_model=ApiEnvelope)
def cancel_queue(req: CancelQueueRequest):
    return _envelope(queue_tool.cancel_queue(req.department, req.queue_number))


@app.get("/api/queue/{department}", response_model=ApiEnvelope)
def queue_status(department: str, queue_number: int | None = Query(None)):
    return _envelope(queue_tool.query_queue(department, queue_number))


# ── 患者 / 症状 ──────────────────────────────────────────────


@app.get("/api/symptoms", response_model=ApiEnvelope)
def list_symptoms():
    return _envelope({"success": True, "symptoms": symptom_tool.get_common_symptoms()})


@app.get("/api/symptoms/lookup", response_model=ApiEnvelope)
def lookup_symptom(symptom: str = Query(..., min_length=1)):
    return _envelope(symptom_tool.lookup_symptom(symptom))


@app.post("/api/patients", response_model=ApiEnvelope)
def create_patient(payload: dict[str, Any]):
    return _envelope(patient_tool.execute("create_patient", payload))


@app.post("/api/patients/query", response_model=ApiEnvelope)
def query_patient(payload: dict[str, Any]):
    return _envelope(patient_tool.execute("query_patient", payload))


# ── 前端静态资源 ─────────────────────────────────────────────


@app.get("/")
def index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="前端资源未找到")
    return FileResponse(index_path)


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)

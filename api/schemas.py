"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID；为空则新建")


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    intent: str = "chitchat"
    confidence: float = 0.0
    agent: Optional[str] = None
    needs_clarification: bool = False
    extracted_info: dict[str, Any] = Field(default_factory=dict)
    collected_info: Optional[dict[str, Any]] = None
    round_count: Optional[int] = None


class SessionActionResponse(BaseModel):
    session_id: str
    ok: bool
    message: str = ""


class ScheduleQuery(BaseModel):
    department: str = Field(..., min_length=1)
    date: Optional[str] = None


class CreateAppointmentRequest(BaseModel):
    department: str
    doctor: str = ""
    date: str
    period: str
    patient_name: str
    phone: str


class AppointmentIdRequest(BaseModel):
    appointment_id: str


class TakeNumberRequest(BaseModel):
    department: str
    patient_name: str


class QueueQueryRequest(BaseModel):
    department: str
    queue_number: Optional[int] = None


class CallNextRequest(BaseModel):
    department: str


class CancelQueueRequest(BaseModel):
    department: str
    queue_number: int


class ApiEnvelope(BaseModel):
    """统一工具层响应包装。"""

    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

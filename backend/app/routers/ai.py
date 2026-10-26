from typing import Any, Optional
from fastapi import APIRouter, Path, Query
from app.ai import ai_client, ai_copilot, ai_diagnostics, automation_ai
from app.database.repository import repo
from app.models import (
    AIChatRequest,
    AIChatResponse,
    AIDiagnosticsResponse,
    AIRuleGenerateRequest,
    AIRuleGenerateResponse,
)
from app.mqtt_client import mqtt_service

router = APIRouter(prefix="/ai", tags=["AI & Copilot"])


@router.post("/copilot", response_model=AIChatResponse, summary="Natural Language IoT Copilot")
async def copilot_chat(body: AIChatRequest):
    """
    Process natural language or voice commands via Llama (Ollama / Groq / SmartDev AI).
    Interprets intent, controls hardware via MQTT, and replies in natural language.
    """
    result = await ai_copilot.execute_prompt(
        prompt=body.prompt,
        target_device_id=body.device_id,
        provider=body.provider,
    )
    return AIChatResponse(**result)


@router.get("/diagnostics/{device_id}", response_model=AIDiagnosticsResponse, summary="AI Predictive Diagnostics & Health Score")
async def get_device_diagnostics(
    device_id: str = Path(..., description="Device identifier to diagnose")
):
    """
    Evaluates WiFi RSSI, Heap memory degradation, CPU load, and boot history.
    Returns 0-100 Health Score, detected anomalies, recommendations, and AI narrative.
    """
    device = mqtt_service.get_device(device_id)
    analysis = await ai_diagnostics.analyze_device(device_id, device.model_dump())
    return AIDiagnosticsResponse(**analysis)


@router.post("/generate-rule", response_model=AIRuleGenerateResponse, summary="Natural Language to Automation Rule")
async def generate_automation_rule(body: AIRuleGenerateRequest):
    """
    Converts a plain English prompt into an executable automation rule for the Rule Engine.
    """
    result = await automation_ai.generate_rule(body.prompt, mqtt_service.get_default_device_id())
    return AIRuleGenerateResponse(**result)


@router.get("/providers", summary="Check AI Provider Status")
async def get_ai_providers():
    """
    Returns availability status for Ollama (Llama), Groq Cloud API, and Builtin Engine.
    """
    return await ai_client.get_available_providers()


@router.get("/history", summary="Get recent AI conversation history")
async def get_ai_history(
    limit: int = Query(default=20, ge=1, le=100),
    device_id: Optional[str] = Query(default=None),
):
    """
    Returns stored history of AI Copilot conversations and executed hardware actions.
    """
    return await repo.get_recent_ai_conversations(limit=limit, device_id=device_id)

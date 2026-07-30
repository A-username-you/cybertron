"""Chat API."""
import json
from typing import Dict, Any
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"
    context: Dict[str, Any] = {}

class ChatResponse(BaseModel):
    response: str
    intent: Dict[str, Any]
    findings: list
    engagement_id: str = None

@router.post("/message", response_model=ChatResponse)
async def chat_message(msg: ChatMessage, request: Request):
    state = request.app.state.cybertron
    ai_orch, memory = state.ai_orchestrator, state.memory
    await memory.add(msg.session_id, "user", msg.message)
    intent = await ai_orch.parse_intent(msg.message, {"session_id": msg.session_id})
    response_parts, findings, engagement_id = [], [], None

    if intent.intent == "scan":
        response_parts.append(f"🔍 **Scanning** `{intent.target}` with plugins: {', '.join(intent.plugins)}")
        response_parts.append(f"💭 *Reasoning:* {intent.reasoning}")
        results = await ai_orch.execute_intent(intent)
        analysis = await ai_orch.analyze_findings([])
        response_parts.append(f"\n📊 **Risk Score:** {analysis.get('risk_score', 0)}/100")
        response_parts.append(f"📝 **Summary:** {analysis.get('summary', 'N/A')}")
        if analysis.get('recommendations'):
            response_parts.append("\n🔧 **Recommendations:**")
            for rec in analysis['recommendations'][:3]:
                response_parts.append(f" • {rec}")
    elif intent.intent == "engage":
        engagement_id = f"AI-{msg.session_id[:8]}"
        response_parts.append(f"🎯 **Engagement started:** `{engagement_id}`")
        response_parts.append(f"Target: `{intent.target}`")
    elif intent.intent == "audit":
        response_parts.append(f"🔎 **Security audit** initiated for `{intent.target}`")
    else:
        response_parts.append(f"🤖 I understood you want to **{intent.intent}** `{intent.target}`.")
        response_parts.append(f"Selected plugins: {', '.join(intent.plugins)}")
        response_parts.append(f"Reasoning: {intent.reasoning}")

    full_response = "\n\n".join(response_parts)
    await memory.add(msg.session_id, "assistant", full_response, {"intent": intent.__dict__})
    return ChatResponse(response=full_response, intent=intent.__dict__, findings=findings, engagement_id=engagement_id)

@router.post("/stream")
async def chat_stream(msg: ChatMessage, request: Request):
    from fastapi.responses import StreamingResponse
    import asyncio
    state = request.app.state.cybertron

    async def event_generator():
        yield f"data: {json.dumps({'type': 'status', 'content': 'Thinking...'})}\n\n"
        await asyncio.sleep(0.5)
        intent = await state.ai_orchestrator.parse_intent(msg.message, {"session_id": msg.session_id})
        yield f"data: {json.dumps({'type': 'intent', 'content': intent.__dict__})}\n\n"
        if intent.intent in ("scan", "audit"):
            yield f"data: {json.dumps({'type': 'status', 'content': f'Running {len(intent.plugins)} plugins...'})}\n\n"
            results = await state.ai_orchestrator.execute_intent(intent)
            yield f"data: {json.dumps({'type': 'progress', 'content': 'Done'})}\n\n"
            analysis = await state.ai_orchestrator.analyze_findings([])
            yield f"data: {json.dumps({'type': 'analysis', 'content': analysis})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

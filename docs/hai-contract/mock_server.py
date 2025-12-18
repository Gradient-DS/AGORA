#!/usr/bin/env python3
"""
Mock server for testing AG-UI Protocol WebSocket communication and REST API.

This server simulates the AGORA orchestrator for frontend testing.
Implements the AG-UI Protocol v2.3.0 with proper event lifecycle.

Features:
- WebSocket: AG-UI Protocol events for real-time communication
- REST API: Session management endpoints for conversation history

Supports Demo Scenario 1: Inspecteur Koen - Restaurant Bella Rosa

Usage:
    python mock_server.py

Endpoints:
    WebSocket: ws://localhost:8000/ws
    REST API:
        GET  /sessions?user_id={user_id}
        GET  /sessions/{session_id}/history?include_tools=true
        GET  /sessions/{session_id}/metadata
        DELETE /sessions/{session_id}
"""

import asyncio
import json
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import websockets
from websockets.http11 import Response


# Agent IDs matching the frontend UI (from HAI/src/stores/useAgentStore.ts)
class Agents:
    GENERAL = "general-agent"  # Algemene Assistent
    HISTORY = "history-agent"  # Bedrijfsinformatie Specialist
    REGULATION = "regulation-agent"  # Regelgeving Specialist
    REPORTING = "reporting-agent"  # Rapportage Specialist


# Demo data for Restaurant Bella Rosa
DEMO_COMPANY = {
    "kvk_number": "92251854",
    "name": "Restaurant Bella Rosa",
    "legal_form": "Besloten Vennootschap",
    "registration_date": "2019-03-15",
    "sbi_codes": ["5610 - Restaurants en mobiele eetgelegenheden"],
    "status": "Actief",
    "address": "Haagweg 123, 2511 AA Den Haag",
}

DEMO_VIOLATION = {
    "date": "15 mei 2022",
    "type": "Onvoldoende hygiënemaatregelen in de keuken",
    "severity": "Waarschuwing",
    "status": "Nog niet opgelost",
    "regulation": "Hygiënecode Horeca artikel 4.2",
    "follow_up_required": True,
    "follow_up_date": "15 augustus 2022",
    "follow_up_executed": False,
}

DEMO_REGULATIONS = [
    {
        "name": "Hygiënecode Horeca artikel 4.2",
        "description": "Hygiënische werkwijze - Bewaren van bederfelijke waar",
    },
    {
        "name": "Warenwetregeling Hygiëne van Levensmiddelen",
        "description": "Bewaartemperaturen bederfelijke waar onder 7°C",
    },
    {
        "name": "EU Verordening 852/2004",
        "description": "Algemene levensmiddelenhygiëne voorschriften",
    },
]


# ---------------------------------------------------------------------------
# MOCK SESSION DATA FOR TESTING
# ---------------------------------------------------------------------------

def get_mock_sessions() -> dict:
    """Return mock session data for demo personas."""
    now = datetime.now()
    return {
        # Koen's sessions
        "session-koen-bella-rosa": {
            "sessionId": "session-koen-bella-rosa",
            "userId": "koen",
            "title": "Inspectie bij Restaurant Bella Rosa",
            "firstMessagePreview": "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854",
            "messageCount": 8,
            "createdAt": (now - timedelta(hours=2)).isoformat() + "Z",
            "lastActivity": (now - timedelta(minutes=30)).isoformat() + "Z",
        },
        "session-koen-hotel-sunset": {
            "sessionId": "session-koen-hotel-sunset",
            "userId": "koen",
            "title": "Inspectie Hotel Sunset",
            "firstMessagePreview": "Start inspectie bij Hotel Sunset, kvk: 12345678",
            "messageCount": 15,
            "createdAt": (now - timedelta(days=2)).isoformat() + "Z",
            "lastActivity": (now - timedelta(days=2, hours=-1)).isoformat() + "Z",
        },
        # Fatima's sessions
        "session-fatima-bakery": {
            "sessionId": "session-fatima-bakery",
            "userId": "fatima",
            "title": "Inspectie Bakkerij De Gouden Korenschoof",
            "firstMessagePreview": "Ik wil een inspectie starten bij Bakkerij De Gouden Korenschoof",
            "messageCount": 6,
            "createdAt": (now - timedelta(days=1)).isoformat() + "Z",
            "lastActivity": (now - timedelta(days=1, hours=-2)).isoformat() + "Z",
        },
        # Jan's sessions
        "session-jan-supermarket": {
            "sessionId": "session-jan-supermarket",
            "userId": "jan",
            "title": "Controle Supermarkt Plus",
            "firstMessagePreview": "Controle bij Supermarkt Plus, ik heb vragen over de koelketen",
            "messageCount": 4,
            "createdAt": (now - timedelta(days=3)).isoformat() + "Z",
            "lastActivity": (now - timedelta(days=3)).isoformat() + "Z",
        },
    }


def get_mock_history(session_id: str, include_tools: bool = False) -> list:
    """Return mock conversation history for a session."""
    if session_id == "session-koen-bella-rosa":
        history = [
            {"role": "user", "content": "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854"},
            {
                "role": "assistant",
                "content": "Inspectie gestart voor **Restaurant Bella Rosa**.\n\n**Bedrijfsgegevens:**\n- KVK: 92251854\n- Rechtsvorm: Besloten Vennootschap\n- Status: Actief\n\n**Inspectiehistorie:**\n⚠️ Er is 1 openstaande overtreding uit 15 mei 2022.",
                "agent_id": Agents.HISTORY
            },
            {"role": "user", "content": "Ik zie een geopende ton met rauwe vis op kamertemperatuur"},
            {
                "role": "assistant",
                "content": "🚨 **ERNSTIGE OVERTREDING GECONSTATEERD**\n\nRauwe vis op kamertemperatuur is een direct risico voor voedselvergiftiging. Bederfelijke levensmiddelen moeten onder 7°C bewaard worden.\n\n**Toepasselijke regelgeving:**\n- Hygiënecode Horeca artikel 4.2\n- Warenwetregeling Hygiëne van Levensmiddelen",
                "agent_id": Agents.REGULATION
            },
        ]

        if include_tools:
            # Insert tool calls at appropriate positions
            history = [
                history[0],  # user message
                {"role": "tool_call", "tool_call_id": "call-001", "tool_name": "get_company_info", "content": '{"kvk_number": "92251854"}', "agent_id": Agents.HISTORY},
                {"role": "tool", "tool_call_id": "call-001", "tool_name": "get_company_info", "content": json.dumps(DEMO_COMPANY, ensure_ascii=False)},
                {"role": "tool_call", "tool_call_id": "call-002", "tool_name": "get_inspection_history", "content": '{"kvk_number": "92251854"}', "agent_id": Agents.HISTORY},
                {"role": "tool", "tool_call_id": "call-002", "tool_name": "get_inspection_history", "content": json.dumps({"violations": [DEMO_VIOLATION]}, ensure_ascii=False)},
                history[1],  # assistant response
                history[2],  # user message
                {"role": "tool_call", "tool_call_id": "call-003", "tool_name": "search_regulations", "content": '{"query": "rauwe vis temperatuur"}', "agent_id": Agents.REGULATION},
                {"role": "tool", "tool_call_id": "call-003", "tool_name": "search_regulations", "content": json.dumps({"regulations": DEMO_REGULATIONS}, ensure_ascii=False)},
                history[3],  # assistant response
            ]

        return history

    elif session_id == "session-koen-hotel-sunset":
        return [
            {"role": "user", "content": "Start inspectie bij Hotel Sunset, kvk: 12345678"},
            {"role": "assistant", "content": "Inspectie gestart voor Hotel Sunset. Bedrijfsgegevens worden opgehaald...", "agent_id": Agents.HISTORY},
            {"role": "user", "content": "Wat zijn de regels voor ontbijtbuffet temperaturen?"},
            {"role": "assistant", "content": "Voor ontbijtbuffetten gelden de volgende temperatuurregels...", "agent_id": Agents.REGULATION},
        ]

    elif session_id == "session-fatima-bakery":
        return [
            {"role": "user", "content": "Ik wil een inspectie starten bij Bakkerij De Gouden Korenschoof"},
            {"role": "assistant", "content": "Prima, ik help u graag met de inspectie. Heeft u het KVK-nummer?", "agent_id": Agents.GENERAL},
            {"role": "user", "content": "Ja, het is 87654321"},
            {"role": "assistant", "content": "Inspectie gestart voor Bakkerij De Gouden Korenschoof.", "agent_id": Agents.HISTORY},
        ]

    elif session_id == "session-jan-supermarket":
        return [
            {"role": "user", "content": "Controle bij Supermarkt Plus, ik heb vragen over de koelketen"},
            {"role": "assistant", "content": "Welkom! Ik help u graag met vragen over de koelketen. Wat wilt u weten?", "agent_id": Agents.GENERAL},
        ]

    return []


# In-memory storage for sessions (can be modified by DELETE)
MOCK_SESSIONS = get_mock_sessions()


def now_timestamp() -> int:
    """Return current timestamp as Unix milliseconds (AG-UI standard)."""
    return int(time.time() * 1000)


def log_event(direction: str, event_type: str, detail: str = "") -> None:
    """Log an event with timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    arrow = "→" if direction == "send" else "←"
    suffix = f" ({detail})" if detail else ""
    print(f"[{timestamp}] {arrow} {event_type}{suffix}")


async def send_event(websocket, event: dict, detail: str = "") -> None:
    """Send an event over WebSocket and log it."""
    log_event("send", event.get("type", "unknown"), detail)
    await websocket.send(json.dumps(event))


class ConversationState:
    """Track conversation state per connection."""

    def __init__(self):
        self.inspection_started = False
        self.company_loaded = False
        self.history_checked = False
        self.findings_recorded = False
        self.regulations_checked = False
        self.pending_approval = None
        self.current_agent = Agents.GENERAL


async def handle_connection(websocket):
    """Handle incoming WebSocket connections."""
    print(f"\n{'='*60}")
    print("Client connected")
    print(f"{'='*60}")

    state = ConversationState()

    try:
        async for message in websocket:
            data = json.loads(message)
            event_type = data.get("type", "RunAgentInput")
            log_event("recv", event_type)

            if data.get("type") == "CUSTOM":
                name = data.get("name", "")
                if name == "agora:tool_approval_response":
                    await handle_approval_response(websocket, data, state)
                    continue
                print(f"  Unknown custom event: {name}")
                continue

            if "threadId" in data or "thread_id" in data:
                await handle_run_input(websocket, data, state)

    except websockets.exceptions.ConnectionClosed:
        print("\nClient disconnected")
        print(f"{'='*60}\n")


async def handle_run_input(websocket, data: dict, state: ConversationState) -> None:
    """Handle a RunAgentInput and simulate an agent response."""
    thread_id = data.get("threadId") or data.get("thread_id") or str(uuid.uuid4())
    run_id = data.get("runId") or data.get("run_id") or str(uuid.uuid4())
    messages = data.get("messages", [])

    user_content = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break

    print(f"  User: {user_content[:60]}{'...' if len(user_content) > 60 else ''}")

    # Always start with algemene-assistent for routing
    await send_run_started(websocket, thread_id, run_id, Agents.GENERAL)
    state.current_agent = Agents.GENERAL

    # Determine which agent should handle this
    content_lower = user_content.lower()

    if is_inspection_start(content_lower):
        target_agent = Agents.HISTORY
    elif is_violation_query(content_lower):
        target_agent = Agents.REGULATION
    elif is_report_request(content_lower):
        target_agent = Agents.REPORTING
    else:
        target_agent = Agents.GENERAL

    # Routing step under algemene-assistent
    await send_step(websocket, "routing", start=True)
    await asyncio.sleep(0.2)
    await send_step(websocket, "routing", start=False)

    # If routing to a specialist, do a handoff tool call
    if target_agent != Agents.GENERAL:
        await send_step(websocket, "executing_tools", start=True)
        await send_handoff_tool_call(websocket, thread_id, run_id, target_agent)
        await send_step(websocket, "executing_tools", start=False)

        # Switch to the specialist agent
        await send_agent_switch(websocket, thread_id, run_id, target_agent)
        state.current_agent = target_agent

    # Route to appropriate handler (they no longer do routing step themselves)
    if is_inspection_start(content_lower):
        await handle_inspection_start(websocket, thread_id, run_id, state, user_content)
    elif is_violation_query(content_lower):
        await handle_finding_input(websocket, thread_id, run_id, state, user_content)
    elif is_report_request(content_lower):
        await handle_report_request(websocket, thread_id, run_id, state)
    else:
        await handle_generic_response(websocket, thread_id, run_id, state, user_content)


def is_inspection_start(content: str) -> bool:
    """Check if message starts an inspection."""
    triggers = ["start inspectie", "inspectie bij", "bella rosa", "92251854"]
    return any(t in content for t in triggers)


def is_violation_query(content: str) -> bool:
    """Check if message describes a violation/finding."""
    triggers = [
        "rauwe vis",
        "temperatuur",
        "afvoerputje",
        "schoonmaak",
        "overtreden",
        "regels",
    ]
    return any(t in content for t in triggers)


def is_report_request(content: str) -> bool:
    """Check if message requests a report."""
    triggers = ["genereer rapport", "rapport", "generate", "report"]
    return any(t in content for t in triggers)


async def send_run_started(websocket, thread_id: str, run_id: str, agent: str) -> None:
    """Send RUN_STARTED and initial STATE_SNAPSHOT with agent."""
    await send_event(
        websocket,
        {
            "type": "RUN_STARTED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_timestamp(),
        },
    )

    await send_event(
        websocket,
        {
            "type": "STATE_SNAPSHOT",
            "snapshot": {
                "threadId": thread_id,
                "runId": run_id,
                "currentAgent": agent,
                "status": "processing",
            },
            "timestamp": now_timestamp(),
        },
        f"agent={agent}",
    )


async def send_agent_switch(websocket, thread_id: str, run_id: str, agent: str) -> None:
    """Send STATE_SNAPSHOT to indicate agent switch."""
    await send_event(
        websocket,
        {
            "type": "STATE_SNAPSHOT",
            "snapshot": {
                "threadId": thread_id,
                "runId": run_id,
                "currentAgent": agent,
                "status": "processing",
            },
            "timestamp": now_timestamp(),
        },
        f"switch to {agent}",
    )


async def send_handoff_tool_call(
    websocket, thread_id: str, run_id: str, target_agent: str
) -> None:
    """Send a transfer_to_agent tool call to show handoff in UI."""
    tool_call_id = f"call-{uuid.uuid4()}"

    agent_descriptions = {
        Agents.HISTORY: "Specialist voor bedrijfsinformatie en KVK-gegevens",
        Agents.REGULATION: "Specialist voor regelgeving en wetanalyse",
        Agents.REPORTING: "Specialist voor het genereren van inspectierapporten",
    }

    await send_tool_call(
        websocket,
        tool_call_id,
        "transfer_to_agent",
        {
            "agent_id": target_agent,
            "reason": agent_descriptions.get(target_agent, "Specialist inschakelen"),
        },
        json.dumps(
            {
                "success": True,
                "transferred_to": target_agent,
                "message": f"Overgedragen aan {target_agent}",
            },
            ensure_ascii=False,
        ),
    )


async def handle_inspection_start(
    websocket, thread_id: str, run_id: str, state: ConversationState, user_content: str
) -> None:
    """Handle inspection start with KVK lookup tool call."""
    state.inspection_started = True
    state.company_loaded = True

    # Tool execution step (routing already done by algemene-assistent)
    await send_step(websocket, "executing_tools", start=True)

    # KVK Lookup tool call
    tool_call_id = f"call-{uuid.uuid4()}"
    await send_tool_call(
        websocket,
        tool_call_id,
        "get_company_info",
        {"kvk_number": DEMO_COMPANY["kvk_number"]},
        json.dumps(DEMO_COMPANY, ensure_ascii=False),
    )

    # Inspection History tool call
    tool_call_id2 = f"call-{uuid.uuid4()}"
    history_result = {
        "total_inspections": 2,
        "last_inspection": "15 mei 2022",
        "violations": [DEMO_VIOLATION],
        "status": "Onder toezicht",
    }
    await send_tool_call(
        websocket,
        tool_call_id2,
        "get_inspection_history",
        {"kvk_number": DEMO_COMPANY["kvk_number"]},
        json.dumps(history_result, ensure_ascii=False),
    )

    await send_step(websocket, "executing_tools", start=False)

    # Thinking and response
    await send_step(websocket, "thinking", start=True)

    response = [
        f"Inspectie gestart voor **{DEMO_COMPANY['name']}**.\n\n",
        f"**Bedrijfsgegevens:**\n",
        f"- KVK: {DEMO_COMPANY['kvk_number']}\n",
        f"- Rechtsvorm: {DEMO_COMPANY['legal_form']}\n",
        f"- Status: {DEMO_COMPANY['status']}\n",
        f"- Sector: {DEMO_COMPANY['sbi_codes'][0]}\n\n",
        f"**Inspectiehistorie:**\n",
        f"⚠️ Er is **1 openstaande overtreding** uit {DEMO_VIOLATION['date']}:\n",
        f"- {DEMO_VIOLATION['type']}\n",
        f"- Ernst: {DEMO_VIOLATION['severity']}\n",
        f"- Status: {DEMO_VIOLATION['status']}\n",
        f"- Follow-up vereist maar nog niet uitgevoerd\n\n",
        f"U kunt nu uw bevindingen doorgeven.",
    ]

    await stream_response(websocket, thread_id, run_id, response, Agents.HISTORY)


async def handle_finding_input(
    websocket, thread_id: str, run_id: str, state: ConversationState, user_content: str
) -> None:
    """Handle violation finding with regulation lookup."""
    state.findings_recorded = True
    state.regulations_checked = True

    # Tool execution (routing already done by algemene-assistent)
    await send_step(websocket, "executing_tools", start=True)

    tool_call_id = f"call-{uuid.uuid4()}"
    await send_tool_call(
        websocket,
        tool_call_id,
        "search_regulations",
        {"query": "bewaren rauwe vis temperatuur hygiëne horeca", "limit": 3},
        json.dumps({"regulations": DEMO_REGULATIONS}, ensure_ascii=False),
    )

    # Check repeat violation
    tool_call_id2 = f"call-{uuid.uuid4()}"
    repeat_result = {
        "is_repeat": True,
        "previous_occurrences": 1,
        "enforcement_recommendation": "IMMEDIATE_ACTION_REQUIRED",
        "escalation_reason": "Herhaalde overtreding met onopgeloste eerdere waarschuwing",
    }
    await send_tool_call(
        websocket,
        tool_call_id2,
        "check_repeat_violation",
        {
            "kvk_number": DEMO_COMPANY["kvk_number"],
            "violation_category": "hygiene_measures",
        },
        json.dumps(repeat_result, ensure_ascii=False),
    )

    await send_step(websocket, "executing_tools", start=False)

    # Thinking and response
    await send_step(websocket, "thinking", start=True)

    response = [
        "🚨 **ERNSTIGE OVERTREDING GECONSTATEERD**\n\n",
        "Uw bevinding betreft meerdere overtredingen:\n\n",
        "**1. Bewaartemperatuur**\n",
        "Rauwe vis op kamertemperatuur is een direct risico voor voedselvergiftiging. ",
        "Bederfelijke levensmiddelen moeten onder 7°C bewaard worden.\n\n",
        "**2. Hygiëne werkplek**\n",
        "Opslag naast afvoerputje met schoonmaakmiddelresten is een kruisbesmettingsrisico.\n\n",
        "**Toepasselijke regelgeving:**\n",
        f"- {DEMO_REGULATIONS[0]['name']}: {DEMO_REGULATIONS[0]['description']}\n",
        f"- {DEMO_REGULATIONS[1]['name']}: {DEMO_REGULATIONS[1]['description']}\n",
        f"- {DEMO_REGULATIONS[2]['name']}: {DEMO_REGULATIONS[2]['description']}\n\n",
        "⚠️ **WAARSCHUWING: Dit is een HERHAALDE overtreding!**\n",
        f"In {DEMO_VIOLATION['date']} was er een soortgelijk probleem dat nog steeds niet is opgelost.\n\n",
        "**Aanbeveling:** Directe handhaving met escalatie wegens recidive.\n\n",
        "Zeg **'Genereer rapport'** om het inspectierapport op te stellen.",
    ]

    await stream_response(websocket, thread_id, run_id, response, Agents.REGULATION)


async def handle_report_request(
    websocket, thread_id: str, run_id: str, state: ConversationState
) -> None:
    """Handle report generation with approval flow (routing already done by algemene-assistent)."""
    # Thinking step
    await send_step(websocket, "thinking", start=True)
    await asyncio.sleep(0.1)
    await send_step(websocket, "thinking", start=False)

    # Tool execution with approval
    await send_step(websocket, "executing_tools", start=True)

    approval_id = f"appr-{uuid.uuid4()}"
    state.pending_approval = {
        "approval_id": approval_id,
        "thread_id": thread_id,
        "run_id": run_id,
    }

    await send_event(
        websocket,
        {
            "type": "CUSTOM",
            "name": "agora:tool_approval_request",
            "value": {
                "toolName": "generate_inspection_report",
                "toolDescription": "Genereert een officieel inspectierapport (PDF) dat permanent wordt opgeslagen en naar het bedrijf wordt verzonden",
                "parameters": {
                    "company_name": DEMO_COMPANY["name"],
                    "kvk_number": DEMO_COMPANY["kvk_number"],
                    "inspector_name": "Koen van der Berg",
                    "include_escalation": True,
                    "violations": [
                        "Bewaartemperatuur overtreding",
                        "Hygiëne overtreding",
                    ],
                },
                "reasoning": "Inspecteur heeft om rapportgeneratie gevraagd na het documenteren van bevindingen",
                "riskLevel": "high",
                "approvalId": approval_id,
            },
            "timestamp": now_timestamp(),
        },
        "tool_approval_request",
    )

    print(f"  ⏳ Wacht op goedkeuring (id: {approval_id[:12]}...)")


async def handle_generic_response(
    websocket, thread_id: str, run_id: str, state: ConversationState, user_content: str
) -> None:
    """Handle generic messages (routing already done, stays with algemene-assistent)."""
    await send_step(websocket, "thinking", start=True)

    if state.inspection_started:
        response = [
            "Ik help u graag verder met de inspectie. ",
            "U kunt:\n",
            "- Bevindingen doorgeven (bijv. 'Ik zie rauwe vis op kamertemperatuur')\n",
            "- Vragen naar regelgeving\n",
            "- Een rapport genereren met 'Genereer rapport'\n",
        ]
    else:
        response = [
            "Welkom bij AGORA. ",
            "Start een inspectie door te zeggen:\n\n",
            "**'Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854'**\n\n",
            "Ik help u vervolgens met:\n",
            "- Bedrijfsgegevens opzoeken\n",
            "- Inspectiehistorie bekijken\n",
            "- Regelgeving raadplegen\n",
            "- Rapport genereren",
        ]

    await stream_response(websocket, thread_id, run_id, response, Agents.GENERAL)


async def handle_approval_response(
    websocket, data: dict, state: ConversationState
) -> None:
    """Handle a tool approval response."""
    value = data.get("value", {})
    approved = value.get("approved", False)
    feedback = value.get("feedback", "")

    pending = state.pending_approval or {}
    thread_id = pending.get("thread_id", str(uuid.uuid4()))
    run_id = pending.get("run_id", str(uuid.uuid4()))

    status = "✅ Goedgekeurd" if approved else "❌ Afgewezen"
    print(f"  {status} (feedback: {feedback or 'geen'})")

    if approved:
        await execute_report_generation(websocket, thread_id, run_id, state)
    else:
        await handle_rejected_report(websocket, thread_id, run_id, state)


async def execute_report_generation(
    websocket, thread_id: str, run_id: str, state: ConversationState
) -> None:
    """Execute report generation after approval."""
    tool_call_id = f"call-{uuid.uuid4()}"
    report_id = f"INS-2024-{uuid.uuid4().hex[:6].upper()}"

    await send_tool_call(
        websocket,
        tool_call_id,
        "generate_inspection_report",
        {
            "company_name": DEMO_COMPANY["name"],
            "kvk_number": DEMO_COMPANY["kvk_number"],
            "inspector_name": "Koen van der Berg",
        },
        json.dumps(
            {
                "success": True,
                "report_id": report_id,
                "filename": f"rapport-{report_id}.pdf",
                "status": "generated",
            }
        ),
    )

    await send_step(websocket, "executing_tools", start=False)
    await send_step(websocket, "thinking", start=True)

    response = [
        f"✅ **Rapport succesvol gegenereerd**\n\n",
        f"**Rapport ID:** {report_id}\n",
        f"**Bestand:** rapport-{report_id}.pdf\n\n",
        f"**Inhoud rapport:**\n",
        f"- Bedrijfsgegevens {DEMO_COMPANY['name']}\n",
        f"- Inspectiehistorie met eerdere overtreding\n",
        f"- Huidige bevindingen (bewaartemperatuur, hygiëne)\n",
        f"- Toepasselijke regelgeving\n",
        f"- ⚠️ Escalatie wegens herhaalde overtreding\n\n",
        f"Het rapport wordt automatisch naar het bedrijf verzonden. ",
        f"De inspectie is afgerond.",
    ]

    await stream_response(websocket, thread_id, run_id, response, Agents.REPORTING)


async def handle_rejected_report(
    websocket, thread_id: str, run_id: str, state: ConversationState
) -> None:
    """Handle rejected report generation."""
    await send_step(websocket, "executing_tools", start=False)
    await send_step(websocket, "thinking", start=True)

    response = [
        "Begrepen, het rapport wordt **niet** gegenereerd.\n\n",
        "U kunt:\n",
        "- Aanvullende bevindingen documenteren\n",
        "- Later alsnog een rapport genereren met 'Genereer rapport'\n",
        "- De inspectie afsluiten zonder rapport",
    ]

    await stream_response(websocket, thread_id, run_id, response, Agents.REPORTING)


async def send_step(websocket, step_name: str, start: bool) -> None:
    """Send a STEP_STARTED or STEP_FINISHED event."""
    event_type = "STEP_STARTED" if start else "STEP_FINISHED"
    await send_event(
        websocket,
        {
            "type": event_type,
            "stepName": step_name,
            "timestamp": now_timestamp(),
        },
        step_name,
    )


async def send_tool_call(
    websocket,
    tool_call_id: str,
    tool_name: str,
    args: dict,
    result: str,
) -> None:
    """Send complete tool call sequence."""
    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_START",
            "toolCallId": tool_call_id,
            "toolCallName": tool_name,
            "parentMessageId": None,
            "timestamp": now_timestamp(),
        },
        tool_name,
    )

    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_ARGS",
            "toolCallId": tool_call_id,
            "delta": json.dumps(args, ensure_ascii=False),
            "timestamp": now_timestamp(),
        },
    )

    await asyncio.sleep(0.3)

    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_END",
            "toolCallId": tool_call_id,
            "timestamp": now_timestamp(),
        },
    )

    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_RESULT",
            "messageId": f"tool-result-{tool_call_id}",
            "toolCallId": tool_call_id,
            "content": result,
            "role": "tool",
            "timestamp": now_timestamp(),
        },
    )


async def stream_response(
    websocket, thread_id: str, run_id: str, content_chunks: list[str], agent: str
) -> None:
    """Stream a text response and finish the run."""
    message_id = f"msg-{uuid.uuid4()}"

    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_START",
            "messageId": message_id,
            "role": "assistant",
            "timestamp": now_timestamp(),
        },
    )

    for chunk in content_chunks:
        await send_event(
            websocket,
            {
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": message_id,
                "delta": chunk,
                "timestamp": now_timestamp(),
            },
        )
        await asyncio.sleep(0.03)

    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_END",
            "messageId": message_id,
            "timestamp": now_timestamp(),
        },
    )

    await send_step(websocket, "thinking", start=False)

    await send_event(
        websocket,
        {
            "type": "STATE_SNAPSHOT",
            "snapshot": {
                "threadId": thread_id,
                "runId": run_id,
                "currentAgent": agent,
                "status": "completed",
            },
            "timestamp": now_timestamp(),
        },
        f"completed by {agent}",
    )

    await send_event(
        websocket,
        {
            "type": "RUN_FINISHED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_timestamp(),
        },
    )


def process_request(connection, request):
    """Handle HTTP requests that aren't WebSocket upgrades.

    Supports:
    - GET /sessions?user_id={user_id}
    - GET /sessions/{session_id}/history?include_tools=true
    - GET /sessions/{session_id}/metadata
    - DELETE /sessions/{session_id}
    - GET /health
    - GET /
    """
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None  # Let WebSocket handler take over

    path = request.path
    method = request.method if hasattr(request, 'method') else "GET"
    parsed = urlparse(path)
    query_params = parse_qs(parsed.query)

    # CORS headers for all responses
    cors_headers = websockets.Headers([
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, DELETE, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
        ("Content-Type", "application/json"),
    ])

    # Handle OPTIONS (CORS preflight)
    if method == "OPTIONS":
        return Response(200, "OK", cors_headers, b"")

    # Health check
    if parsed.path == "/health":
        body = json.dumps({"status": "healthy", "service": "agora-mock", "protocol": "ag-ui"})
        return Response(200, "OK", cors_headers, body.encode())

    # Root endpoint
    if parsed.path == "/":
        body = json.dumps({
            "service": "AGORA Mock Server",
            "version": "2.3.0",
            "protocol": "AG-UI Protocol v2.3.0",
            "endpoints": {
                "websocket": "/ws",
                "sessions": "/sessions?user_id={user_id}",
                "history": "/sessions/{id}/history?include_tools=true",
            }
        })
        return Response(200, "OK", cors_headers, body.encode())

    # GET /sessions - List sessions for a user
    if parsed.path == "/sessions" and method == "GET":
        user_id = query_params.get("user_id", [None])[0]
        if not user_id:
            body = json.dumps({"success": False, "error": "user_id is required"})
            return Response(400, "Bad Request", cors_headers, body.encode())

        # Filter sessions by user_id
        user_sessions = [
            session for session in MOCK_SESSIONS.values()
            if session["userId"] == user_id
        ]
        # Sort by lastActivity descending
        user_sessions.sort(key=lambda s: s["lastActivity"], reverse=True)

        body = json.dumps({
            "success": True,
            "sessions": user_sessions,
            "totalCount": len(user_sessions),
        }, ensure_ascii=False)
        log_event("send", "HTTP", f"GET /sessions?user_id={user_id} -> {len(user_sessions)} sessions")
        return Response(200, "OK", cors_headers, body.encode())

    # Match /sessions/{session_id}/history
    history_match = re.match(r"^/sessions/([^/]+)/history$", parsed.path)
    if history_match and method == "GET":
        session_id = history_match.group(1)
        include_tools = query_params.get("include_tools", ["false"])[0].lower() == "true"

        if session_id not in MOCK_SESSIONS:
            body = json.dumps({"success": False, "error": "Session not found"})
            return Response(404, "Not Found", cors_headers, body.encode())

        history = get_mock_history(session_id, include_tools)
        body = json.dumps({
            "success": True,
            "threadId": session_id,
            "history": history,
            "messageCount": len(history),
        }, ensure_ascii=False)
        log_event("send", "HTTP", f"GET /sessions/{session_id}/history -> {len(history)} messages")
        return Response(200, "OK", cors_headers, body.encode())

    # Match /sessions/{session_id}/metadata
    metadata_match = re.match(r"^/sessions/([^/]+)/metadata$", parsed.path)
    if metadata_match and method == "GET":
        session_id = metadata_match.group(1)

        if session_id not in MOCK_SESSIONS:
            body = json.dumps({"success": False, "error": "Session not found"})
            return Response(404, "Not Found", cors_headers, body.encode())

        body = json.dumps({
            "success": True,
            "session": MOCK_SESSIONS[session_id],
        }, ensure_ascii=False)
        log_event("send", "HTTP", f"GET /sessions/{session_id}/metadata")
        return Response(200, "OK", cors_headers, body.encode())

    # Match DELETE /sessions/{session_id}
    delete_match = re.match(r"^/sessions/([^/]+)$", parsed.path)
    if delete_match and method == "DELETE":
        session_id = delete_match.group(1)

        if session_id not in MOCK_SESSIONS:
            body = json.dumps({"detail": "Session not found"})
            return Response(404, "Not Found", cors_headers, body.encode())

        del MOCK_SESSIONS[session_id]
        body = json.dumps({
            "success": True,
            "message": "Session deleted",
        })
        log_event("send", "HTTP", f"DELETE /sessions/{session_id}")
        return Response(200, "OK", cors_headers, body.encode())

    # Default: Unknown endpoint
    body = json.dumps({"error": "Not found", "path": parsed.path})
    return Response(404, "Not Found", cors_headers, body.encode())


async def main():
    """Start the mock WebSocket server with REST API support."""
    print()
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║       AG-UI Protocol Mock Server v2.3.0 - Demo Mode            ║")
    print("╠════════════════════════════════════════════════════════════════╣")
    print("║  WebSocket: ws://localhost:8000/ws                             ║")
    print("║  REST API:  http://localhost:8000                              ║")
    print("║  Press Ctrl+C to stop                                          ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    print("REST API Endpoints:")
    print("  GET  /sessions?user_id={user_id}       - List sessions")
    print("  GET  /sessions/{id}/history            - Get conversation history")
    print("  GET  /sessions/{id}/metadata           - Get session metadata")
    print("  DELETE /sessions/{id}                  - Delete session")
    print()
    print("Mock Sessions (for testing):")
    print("  • koen: 2 sessions (Bella Rosa, Hotel Sunset)")
    print("  • fatima: 1 session (Bakkerij)")
    print("  • jan: 1 session (Supermarkt)")
    print()
    print("Test the REST API:")
    print("  curl http://localhost:8000/sessions?user_id=koen")
    print("  curl http://localhost:8000/sessions/session-koen-bella-rosa/history?include_tools=true")
    print()
    print("─" * 64)
    print()
    print("Demo Scenario: Inspecteur Koen - Restaurant Bella Rosa")
    print()
    print("Agents:")
    print(f"  • {Agents.GENERAL}")
    print(f"  • {Agents.HISTORY}")
    print(f"  • {Agents.REGULATION}")
    print(f"  • {Agents.REPORTING}")
    print()
    print("Test inputs (copy-paste these):")
    print()
    print("  1. Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854")
    print(f"     → Routes to: {Agents.HISTORY} (Bedrijfsinformatie Specialist)")
    print()
    print("  2. Ik zie een geopende ton met rauwe vis op kamertemperatuur naast")
    print("     een afvoerputje vol schoonmaakmiddelresten, welke regels worden")
    print("     hiermee overtreden?")
    print(f"     → Routes to: {Agents.REGULATION} (Regelgeving Specialist)")
    print()
    print("  3. Genereer rapport")
    print(
        f"     → Routes to: {Agents.REPORTING} (Rapportage Specialist, with approval)"
    )
    print()

    async with websockets.serve(
        handle_connection,
        "localhost",
        8000,
        process_request=process_request,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")

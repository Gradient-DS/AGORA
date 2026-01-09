#!/usr/bin/env python3
"""
Mock server for testing AG-UI Protocol WebSocket communication and REST API.

This server simulates the AGORA orchestrator for frontend testing.
Implements the AG-UI Protocol v2.4.2 with AGORA extensions.

Features:
- WebSocket: AG-UI Protocol events for real-time communication
- REST API: Session and user management endpoints
- AGORA Extensions: userId in RunAgentInput, spoken text events, HITL approval

Supports Demo Scenario 1: Inspecteur Koen - Restaurant Bella Rosa

Usage:
    python mock_server.py

WebSocket Input (RunAgentInput):
    {
        "threadId": "session-uuid",
        "runId": "run-uuid",
        "userId": "user-uuid",  # AGORA extension - required
        "messages": [{"role": "user", "content": "..."}]
    }

Endpoints:
    WebSocket: ws://localhost:8000/ws
    REST API - Sessions:
        GET  /sessions?user_id={user_id}
        GET  /sessions/{session_id}/history?include_tools=true
        GET  /sessions/{session_id}/metadata
        DELETE /sessions/{session_id}
    REST API - Users:
        GET  /users/me
        PUT  /users/me/preferences
        POST /users
        GET  /users
        GET  /users/{user_id}
        PUT  /users/{user_id}
        DELETE /users/{user_id}
"""

import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote
from http import HTTPStatus

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
            {
                "role": "user",
                "content": "Start inspectie bij Restaurant Bella Rosa, kvk nummer: 92251854",
            },
            {
                "role": "assistant",
                "content": "Inspectie gestart voor **Restaurant Bella Rosa**.\n\n**Bedrijfsgegevens:**\n- KVK: 92251854\n- Rechtsvorm: Besloten Vennootschap\n- Status: Actief\n\n**Inspectiehistorie:**\n⚠️ Er is 1 openstaande overtreding uit 15 mei 2022.",
                "agent_id": Agents.HISTORY,
            },
            {
                "role": "user",
                "content": "Ik zie een geopende ton met rauwe vis op kamertemperatuur",
            },
            {
                "role": "assistant",
                "content": "🚨 **ERNSTIGE OVERTREDING GECONSTATEERD**\n\nRauwe vis op kamertemperatuur is een direct risico voor voedselvergiftiging. Bederfelijke levensmiddelen moeten onder 7°C bewaard worden.\n\n**Toepasselijke regelgeving:**\n- Hygiënecode Horeca artikel 4.2\n- Warenwetregeling Hygiëne van Levensmiddelen",
                "agent_id": Agents.REGULATION,
            },
        ]

        if include_tools:
            # Insert tool calls at appropriate positions
            history = [
                history[0],  # user message
                {
                    "role": "tool_call",
                    "tool_call_id": "call-001",
                    "tool_name": "get_company_info",
                    "content": '{"kvk_number": "92251854"}',
                    "agent_id": Agents.HISTORY,
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-001",
                    "tool_name": "get_company_info",
                    "content": json.dumps(DEMO_COMPANY, ensure_ascii=False),
                },
                {
                    "role": "tool_call",
                    "tool_call_id": "call-002",
                    "tool_name": "get_inspection_history",
                    "content": '{"kvk_number": "92251854"}',
                    "agent_id": Agents.HISTORY,
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-002",
                    "tool_name": "get_inspection_history",
                    "content": json.dumps(
                        {"violations": [DEMO_VIOLATION]}, ensure_ascii=False
                    ),
                },
                history[1],  # assistant response
                history[2],  # user message
                {
                    "role": "tool_call",
                    "tool_call_id": "call-003",
                    "tool_name": "search_regulations",
                    "content": '{"query": "rauwe vis temperatuur"}',
                    "agent_id": Agents.REGULATION,
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-003",
                    "tool_name": "search_regulations",
                    "content": json.dumps(
                        {"regulations": DEMO_REGULATIONS}, ensure_ascii=False
                    ),
                },
                history[3],  # assistant response
            ]

        return history

    elif session_id == "session-koen-hotel-sunset":
        return [
            {
                "role": "user",
                "content": "Start inspectie bij Hotel Sunset, kvk: 12345678",
            },
            {
                "role": "assistant",
                "content": "Inspectie gestart voor Hotel Sunset. Bedrijfsgegevens worden opgehaald...",
                "agent_id": Agents.HISTORY,
            },
            {
                "role": "user",
                "content": "Wat zijn de regels voor ontbijtbuffet temperaturen?",
            },
            {
                "role": "assistant",
                "content": "Voor ontbijtbuffetten gelden de volgende temperatuurregels...",
                "agent_id": Agents.REGULATION,
            },
        ]

    elif session_id == "session-fatima-bakery":
        return [
            {
                "role": "user",
                "content": "Ik wil een inspectie starten bij Bakkerij De Gouden Korenschoof",
            },
            {
                "role": "assistant",
                "content": "Prima, ik help u graag met de inspectie. Heeft u het KVK-nummer?",
                "agent_id": Agents.GENERAL,
            },
            {"role": "user", "content": "Ja, het is 87654321"},
            {
                "role": "assistant",
                "content": "Inspectie gestart voor Bakkerij De Gouden Korenschoof.",
                "agent_id": Agents.HISTORY,
            },
        ]

    elif session_id == "session-jan-supermarket":
        return [
            {
                "role": "user",
                "content": "Controle bij Supermarkt Plus, ik heb vragen over de koelketen",
            },
            {
                "role": "assistant",
                "content": "Welkom! Ik help u graag met vragen over de koelketen. Wat wilt u weten?",
                "agent_id": Agents.GENERAL,
            },
        ]

    return []


# In-memory storage for sessions (can be modified by DELETE)
MOCK_SESSIONS = get_mock_sessions()


# ---------------------------------------------------------------------------
# MOCK USER DATA FOR TESTING
# ---------------------------------------------------------------------------


def get_mock_users() -> dict:
    """Return mock user data for demo personas."""
    now = datetime.now()
    return {
        "550e8400-e29b-41d4-a716-446655440001": {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "email": "koen.vandenberg@nvwa.nl",
            "name": "Koen van den Berg",
            "preferences": {
                "theme": "light",
                "notifications_enabled": True,
                "default_agent_id": "general-agent",
                "language": "nl-NL",
                "spoken_text_type": "summarize",
            },
            "createdAt": "2024-06-15T09:00:00Z",
            "lastActivity": (now - timedelta(minutes=30)).isoformat() + "Z",
        },
        "550e8400-e29b-41d4-a716-446655440002": {
            "id": "550e8400-e29b-41d4-a716-446655440002",
            "email": "fatima.el-amrani@nvwa.nl",
            "name": "Fatima El-Amrani",
            "preferences": {
                "theme": "dark",
                "notifications_enabled": True,
                "default_agent_id": "general-agent",
                "language": "nl-NL",
                "spoken_text_type": "dictate",
            },
            "createdAt": "2024-08-20T14:30:00Z",
            "lastActivity": (now - timedelta(days=1)).isoformat() + "Z",
        },
        "550e8400-e29b-41d4-a716-446655440003": {
            "id": "550e8400-e29b-41d4-a716-446655440003",
            "email": "jan.devries@nvwa.nl",
            "name": "Jan de Vries",
            "preferences": {
                "theme": "system",
                "notifications_enabled": False,
                "default_agent_id": "general-agent",
                "language": "nl-NL",
                "spoken_text_type": "summarize",
            },
            "createdAt": "2024-01-10T08:00:00Z",
            "lastActivity": (now - timedelta(days=3)).isoformat() + "Z",
        },
    }


# In-memory storage for users (can be modified by CRUD operations)
MOCK_USERS = get_mock_users()

# Map of legacy userIds to new UUID-based user IDs (for session compatibility)
USER_ID_MAP = {
    "koen": "550e8400-e29b-41d4-a716-446655440001",
    "fatima": "550e8400-e29b-41d4-a716-446655440002",
    "jan": "550e8400-e29b-41d4-a716-446655440003",
}

# Default "current user" for /users/me endpoint (simulates authenticated user)
CURRENT_USER_ID = "550e8400-e29b-41d4-a716-446655440001"


def now_timestamp() -> int:
    """Return current timestamp as Unix milliseconds (AG-UI standard)."""
    return int(time.time() * 1000)


def to_spoken_text(text: str) -> str:
    """Convert markdown text to speech-friendly text with Dutch expansions."""
    # Remove markdown formatting
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # Bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)  # Italic
    text = re.sub(r"`([^`]+)`", r"\1", text)  # Code
    text = text.replace("- ", "")  # List bullets

    # Emoji replacements
    text = text.replace("⚠️", "Let op: ")
    text = text.replace("🚨", "Waarschuwing: ")
    text = text.replace("✅", "")

    # Dutch abbreviation expansions
    text = re.sub(r"KVK", "Kamer van Koophandel", text, flags=re.IGNORECASE)
    text = re.sub(r"NVWA", "Nederlandse Voedsel- en Warenautoriteit", text, flags=re.IGNORECASE)
    text = re.sub(r"°C", " graden Celsius", text, flags=re.IGNORECASE)
    text = re.sub(r"EU", "Europese Unie", text, flags=re.IGNORECASE)
    text = re.sub(r"PDF", "P D F", text, flags=re.IGNORECASE)
    text = re.sub(r"ID", "I D", text, flags=re.IGNORECASE)

    return text.strip()


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
    user_id = data.get("userId") or data.get("user_id")
    messages = data.get("messages", [])

    user_content = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break

    # Log user info if provided
    user_info = f" (user: {user_id})" if user_id else ""
    print(f"  User{user_info}: {user_content[:60]}{'...' if len(user_content) > 60 else ''}")

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
    await asyncio.sleep(0.5)
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

    tool_descriptions = {
        Agents.HISTORY: "Ik schakel de bedrijfsinformatie specialist in",
        Agents.REGULATION: "Ik schakel de regelgeving specialist in",
        Agents.REPORTING: "Ik schakel de rapportage specialist in",
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
        tool_description=tool_descriptions.get(
            target_agent, "Ik schakel een specialist in"
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
                "download_urls": {
                    "json": "http://localhost:8000/mock_documents/report.json",
                    "pdf": "http://localhost:8000/mock_documents/report.pdf",
                },
                "status": "generated",
            }
        ),
    )

    await send_step(websocket, "executing_tools", start=False)
    await send_step(websocket, "thinking", start=True)

    response = [
        f"✅ **Rapport succesvol gegenereerd**\n\n",
        f"**Rapport ID:** {report_id}\n\n",
        f"**Downloads:**\n",
        f"- [PDF Rapport](http://localhost:8000/mock_documents/report.pdf)\n",
        f"- [JSON Data](http://localhost:8000/mock_documents/report.json)\n\n",
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
    tool_description: str | None = None,
) -> None:
    """Send complete tool call sequence."""
    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_START",
            "toolCallId": tool_call_id,
            "toolCallName": tool_name,
            "toolDescription": tool_description,
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
    """Stream a text response with parallel spoken text and finish the run."""
    message_id = f"msg-{uuid.uuid4()}"
    
    # Check user preference for spoken_text_type
    user = MOCK_USERS[CURRENT_USER_ID]
    spoken_text_type = "dictate"  # default
    if user:
        user_prefs = user.get("preferences", {})
        spoken_text_type = user_prefs.get("spoken_text_type", "dictate")

    # Start both text and spoken message streams
    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_START",
            "messageId": message_id,
            "role": "assistant",
            "timestamp": now_timestamp(),
        },
    )

    await send_event(
        websocket,
        {
            "type": "CUSTOM",
            "name": "agora:spoken_text_start",
            "value": {
                "messageId": message_id,
                "role": "assistant",
            },
            "timestamp": now_timestamp(),
        },
        "agora:spoken_text_start",
    )

    for index, chunk in enumerate(content_chunks):
        # Send regular text chunk (always send all chunks)
        await send_event(
            websocket,
            {
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": message_id,
                "delta": chunk,
                "timestamp": now_timestamp(),
            },
        )

        # Send spoken text chunk (simplified for TTS)
        # If spoken_text_type is "summarize", only send first chunk
        should_send_spoken = (spoken_text_type == "dictate") or (spoken_text_type == "summarize" and index == 0)
        
        if should_send_spoken:
            spoken_chunk = to_spoken_text(chunk)
            if spoken_chunk:
                await send_event(
                    websocket,
                    {
                        "type": "CUSTOM",
                        "name": "agora:spoken_text_content",
                        "value": {
                            "messageId": message_id,
                            "delta": spoken_chunk,
                        },
                        "timestamp": now_timestamp(),
                    },
                )

        await asyncio.sleep(0.1)

    # End both text and spoken message streams
    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_END",
            "messageId": message_id,
            "timestamp": now_timestamp(),
        },
    )

    await send_event(
        websocket,
        {
            "type": "CUSTOM",
            "name": "agora:spoken_text_end",
            "value": {
                "messageId": message_id,
            },
            "timestamp": now_timestamp(),
        },
        "agora:spoken_text_end",
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


async def handle_http_request(reader, writer):
    """Handle a single HTTP request using asyncio streams."""
    try:
        # Read request line
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            await writer.wait_closed()
            return
        
        request_line = request_line.decode('utf-8').strip()
        parts = request_line.split() # Method, Path, Version
        if len(parts) < 2:
            writer.close()
            await writer.wait_closed()
            return
        
        method = parts[0]
        full_path = parts[1]
        
        # Parse path and query
        parsed = urlparse(full_path)
        path = unquote(parsed.path)
        query_params = parse_qs(parsed.query)
        
        # Read headers
        headers = {}
        while True:
            line = await reader.readline()
            if line == b'\r\n' or line == b'\n':
                break
            if line:
                header_line = line.decode('utf-8').strip()
                if ':' in header_line:
                    key, value = header_line.split(':', 1)
                    headers[key.strip().lower()] = value.strip()
        
        # Read body if present
        body = b''
        if 'content-length' in headers:
            content_length = int(headers['content-length'])
            body = await reader.read(content_length)
        
        # Parse body as JSON if applicable
        request_body = {}
        if body and headers.get('content-type', '').startswith('application/json'):
            try:
                request_body = json.loads(body.decode('utf-8'))
            except:
                pass
        
        # Route the request
        response_data, status_code, content_type = await route_http_request(
            method, path, query_params, request_body
        )
        
        # Send response
        await send_http_response(writer, status_code, response_data, content_type)
        
    except Exception as e:
        print(f"HTTP Error: {e}")
        try:
            await send_http_response(writer, 500, {"error": "Internal server error"}, "application/json")
        except:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass


async def send_http_response(writer, status_code, data, content_type="application/json"):
    """Send an HTTP response."""
    # Prepare body
    if isinstance(data, (dict, list)):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    elif isinstance(data, bytes):
        body = data
    else:
        body = str(data).encode('utf-8')
    
    # Build response
    status_text = HTTPStatus(status_code).phrase
    response = f"HTTP/1.1 {status_code} {status_text}\r\n"
    response += f"Content-Type: {content_type}\r\n"
    response += f"Content-Length: {len(body)}\r\n"
    response += "Access-Control-Allow-Origin: *\r\n"
    response += "Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS\r\n"
    response += "Access-Control-Allow-Headers: Content-Type\r\n"
    
    # Add disposition header for downloads
    if "mock_documents" in str(data):
        filename = str(data).split("/")[-1] if "/" in str(data) else "file"
        response += f'Content-Disposition: attachment; filename="{filename}"\r\n'
    
    response += "\r\n"
    
    writer.write(response.encode('utf-8'))
    writer.write(body)
    await writer.drain()


async def route_http_request(method, path, query_params, request_body):
    """Route HTTP request to appropriate handler.
    
    Returns: (response_data, status_code, content_type)
    """
    # Handle OPTIONS (CORS preflight)
    if method == "OPTIONS":
        return {}, 200, "application/json"
    
    # Root endpoint
    if path == "/":
        return {
            "service": "AGORA Mock Server",
            "version": "2.4.0",
            "protocol": "AG-UI Protocol v2.4.0",
            "endpoints": {
                "websocket": "ws://localhost:8000/ws",
                "sessions": "http://localhost:8001/sessions?user_id={user_id}",
                "history": "http://localhost:8001/sessions/{id}/history?include_tools=true",
                "users": "http://localhost:8001/users",
                "currentUser": "http://localhost:8001/users/me",
            },
        }, 200, "application/json"
    
    # Health check
    if path == "/health":
        return {
            "status": "healthy",
            "service": "agora-mock",
            "protocol": "ag-ui"
        }, 200, "application/json"
    
    # GET /sessions
    if path == "/sessions" and method == "GET":
        user_id = query_params.get("user_id", [None])[0]
        if not user_id:
            return {"success": False, "error": "user_id is required"}, 400, "application/json"
        
        user_sessions = [
            session for session in MOCK_SESSIONS.values()
            if session["userId"] == user_id
        ]
        user_sessions.sort(key=lambda s: s["lastActivity"], reverse=True)
        
        log_event("send", "HTTP", f"GET /sessions?user_id={user_id} -> {len(user_sessions)} sessions")
        return {
            "success": True,
            "sessions": user_sessions,
            "totalCount": len(user_sessions),
        }, 200, "application/json"
    
    # GET /sessions/{id}/history
    history_match = re.match(r"^/sessions/([^/]+)/history$", path)
    if history_match and method == "GET":
        session_id = history_match.group(1)
        include_tools = query_params.get("include_tools", ["false"])[0].lower() == "true"
        
        if session_id not in MOCK_SESSIONS:
            return {"success": False, "error": "Session not found"}, 404, "application/json"
        
        history = get_mock_history(session_id, include_tools)
        log_event("send", "HTTP", f"GET /sessions/{session_id}/history -> {len(history)} messages")
        return {
            "success": True,
            "threadId": session_id,
            "history": history,
            "messageCount": len(history),
        }, 200, "application/json"
    
    # GET /sessions/{id}/metadata
    metadata_match = re.match(r"^/sessions/([^/]+)/metadata$", path)
    if metadata_match and method == "GET":
        session_id = metadata_match.group(1)
        
        if session_id not in MOCK_SESSIONS:
            return {"success": False, "error": "Session not found"}, 404, "application/json"
        
        log_event("send", "HTTP", f"GET /sessions/{session_id}/metadata")
        return {
            "success": True,
            "session": MOCK_SESSIONS[session_id],
        }, 200, "application/json"
    
    # DELETE /sessions/{id}
    delete_match = re.match(r"^/sessions/([^/]+)$", path)
    if delete_match and method == "DELETE":
        session_id = delete_match.group(1)
        
        if session_id not in MOCK_SESSIONS:
            return {"detail": "Session not found"}, 404, "application/json"
        
        del MOCK_SESSIONS[session_id]
        log_event("send", "HTTP", f"DELETE /sessions/{session_id}")
        return {
            "success": True,
            "message": "Session deleted",
        }, 200, "application/json"
    
    # GET /users/me
    if path == "/users/me" and method == "GET":
        if CURRENT_USER_ID not in MOCK_USERS:
            return {
                "success": False,
                "error": "unauthorized",
                "message": "User not found"
            }, 401, "application/json"
        
        user = MOCK_USERS[CURRENT_USER_ID]
        log_event("send", "HTTP", f"GET /users/me -> {user['name']}")
        return user, 200, "application/json"
    
    # PUT /users/me/preferences
    if path == "/users/me/preferences" and method == "PUT":
        if CURRENT_USER_ID not in MOCK_USERS:
            return {
                "success": False,
                "error": "unauthorized",
                "message": "User not found"
            }, 401, "application/json"
        
        user = MOCK_USERS[CURRENT_USER_ID]
        if "preferences" not in user:
            user["preferences"] = {}
        
        for key in ["theme", "notifications_enabled", "default_agent_id", "language"]:
            if key in request_body:
                user["preferences"][key] = request_body[key]
        
        log_event("send", "HTTP", "PUT /users/me/preferences")
        return {
            "success": True,
            "preferences": user["preferences"],
        }, 200, "application/json"
    
    # POST /users
    if path == "/users" and method == "POST":
        if not request_body.get("email") or not request_body.get("name"):
            return {
                "success": False,
                "error": "bad_request",
                "message": "email and name are required",
            }, 400, "application/json"
        
        email = request_body["email"]
        for existing_user in MOCK_USERS.values():
            if existing_user["email"] == email:
                return {
                    "success": False,
                    "error": "conflict",
                    "message": "Email already exists",
                }, 409, "application/json"
        
        new_user_id = str(uuid.uuid4())
        now = datetime.now()
        new_user = {
            "id": new_user_id,
            "email": email,
            "name": request_body["name"],
            "preferences": {
                "theme": "system",
                "notifications_enabled": True,
                "default_agent_id": "general-agent",
                "language": "nl-NL",
            },
            "createdAt": now.isoformat() + "Z",
            "lastActivity": now.isoformat() + "Z",
        }
        MOCK_USERS[new_user_id] = new_user
        
        log_event("send", "HTTP", f"POST /users -> created {new_user['email']}")
        return {"success": True, "user": new_user}, 201, "application/json"
    
    # GET /users (list)
    if path == "/users" and method == "GET":
        limit = int(query_params.get("limit", [50])[0])
        offset = int(query_params.get("offset", [0])[0])
        
        all_users = list(MOCK_USERS.values())
        all_users.sort(key=lambda u: u["createdAt"], reverse=True)
        paginated_users = all_users[offset : offset + limit]
        
        log_event("send", "HTTP", f"GET /users -> {len(paginated_users)} of {len(all_users)} users")
        return {
            "success": True,
            "users": paginated_users,
            "totalCount": len(all_users),
        }, 200, "application/json"
    
    # GET /users/{id}
    user_get_match = re.match(r"^/users/([^/]+)$", path)
    if user_get_match and method == "GET":
        user_id = user_get_match.group(1)
        
        if user_id not in MOCK_USERS:
            return {
                "success": False,
                "error": "not_found",
                "message": "User not found",
            }, 404, "application/json"
        
        log_event("send", "HTTP", f"GET /users/{user_id}")
        return {
            "success": True,
            "user": MOCK_USERS[user_id],
        }, 200, "application/json"
    
    # PUT /users/{id}
    user_put_match = re.match(r"^/users/([^/]+)$", path)
    if user_put_match and method == "PUT":
        user_id = user_put_match.group(1)
        
        if user_id not in MOCK_USERS:
            return {
                "success": False,
                "error": "not_found",
                "message": "User not found",
            }, 404, "application/json"
        
        user = MOCK_USERS[user_id]
        if "name" in request_body:
            user["name"] = request_body["name"]
        if "preferences" in request_body:
            if "preferences" not in user:
                user["preferences"] = {}
            for key in ["theme", "notifications_enabled", "default_agent_id", "language"]:
                if key in request_body["preferences"]:
                    user["preferences"][key] = request_body["preferences"][key]
        
        log_event("send", "HTTP", f"PUT /users/{user_id}")
        return {"success": True, "user": user}, 200, "application/json"
    
    # DELETE /users/{id}
    user_delete_match = re.match(r"^/users/([^/]+)$", path)
    if user_delete_match and method == "DELETE":
        user_id = user_delete_match.group(1)
        
        if user_id not in MOCK_USERS:
            return {
                "success": False,
                "error": "not_found",
                "message": "User not found",
            }, 404, "application/json"
        
        # Find legacy userId and cascade delete sessions
        legacy_user_id = None
        for legacy_id, uuid_id in USER_ID_MAP.items():
            if uuid_id == user_id:
                legacy_user_id = legacy_id
                break
        
        deleted_sessions_count = 0
        sessions_to_delete = []
        for session_id, session in MOCK_SESSIONS.items():
            if session["userId"] == legacy_user_id or session["userId"] == user_id:
                sessions_to_delete.append(session_id)
        
        for session_id in sessions_to_delete:
            del MOCK_SESSIONS[session_id]
            deleted_sessions_count += 1
        
        del MOCK_USERS[user_id]
        
        log_event("send", "HTTP", f"DELETE /users/{user_id} -> {deleted_sessions_count} sessions deleted")
        return {
            "success": True,
            "message": "User and associated sessions deleted",
            "deletedSessionsCount": deleted_sessions_count,
        }, 200, "application/json"
    
    # GET /mock_documents/{filename}
    doc_match = re.match(r"^/mock_documents/([^/]+)$", path)
    if doc_match and method == "GET":
        filename = doc_match.group(1)
        
        allowed_files = {"report.json", "report.pdf"}
        if filename not in allowed_files:
            return {"error": "File not found"}, 404, "application/json"
        
        mock_docs_dir = Path(__file__).parent / "mock_documents"
        file_path = mock_docs_dir / filename
        
        if not file_path.exists():
            return {"error": "File not found on disk"}, 404, "application/json"
        
        with open(file_path, "rb") as f:
            file_content = f.read()
        
        content_type = "application/json" if filename.endswith(".json") else "application/pdf"
        log_event("send", "HTTP", f"GET /mock_documents/{filename} -> {len(file_content)} bytes")
        return file_content, 200, content_type
    
    # Not found
    return {"error": "Not found", "path": path}, 404, "application/json"

async def main():
    """Start the mock WebSocket server and REST API server."""
    print()
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║       AG-UI Protocol Mock Server v2.4.0 - Demo Mode            ║")
    print("╠════════════════════════════════════════════════════════════════╣")
    print("║  WebSocket: ws://localhost:8000/ws                             ║")
    print("║  REST API:  http://localhost:8001                              ║")
    print("║  Press Ctrl+C to stop                                          ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    print("REST API Endpoints:")
    print()
    print("  Sessions:")
    print("    GET  /sessions?user_id={user_id}       - List sessions")
    print("    GET  /sessions/{id}/history            - Get conversation history")
    print("    GET  /sessions/{id}/metadata           - Get session metadata")
    print("    DELETE /sessions/{id}                  - Delete session")
    print()
    print("  Users:")
    print("    GET  /users/me                         - Get current user")
    print("    PUT  /users/me/preferences             - Update preferences")
    print("    POST /users                            - Create new user")
    print("    GET  /users                            - List all users")
    print("    GET  /users/{id}                       - Get user by ID")
    print("    PUT  /users/{id}                       - Update user")
    print("    DELETE /users/{id}                     - Delete user")
    print()
    print("Mock Data (for testing):")
    print("  Sessions:")
    print("    • koen: 2 sessions (Bella Rosa, Hotel Sunset)")
    print("    • fatima: 1 session (Bakkerij)")
    print("    • jan: 1 session (Supermarkt)")
    print("  Users:")
    print("    • Koen van den Berg (koen.vandenberg@nvwa.nl)")
    print("    • Fatima El-Amrani (fatima.el-amrani@nvwa.nl)")
    print("    • Jan de Vries (jan.devries@nvwa.nl)")
    print()
    print("Test the REST API:")
    print("  curl http://localhost:8001/sessions?user_id=koen")
    print("  curl http://localhost:8001/users/me")
    print("  curl http://localhost:8001/users")
    print(
        "  curl http://localhost:8001/sessions/session-koen-bella-rosa/history?include_tools=true"
    )
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

    # Start REST API server on port 8001
    http_server = await asyncio.start_server(
        handle_http_request,
        "localhost",
        8001
    )
    print("✓ REST API server started on http://localhost:8001")

    # Start WebSocket server on port 8000
    async with websockets.serve(
        handle_connection,
        "localhost",
        8000,
    ):
        print("✓ WebSocket server started on ws://localhost:8000/ws")
        print()
        async with http_server:
            await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")

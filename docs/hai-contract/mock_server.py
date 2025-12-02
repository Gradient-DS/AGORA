#!/usr/bin/env python3
"""
Mock server for testing AG-UI Protocol WebSocket communication.

This server simulates the AGORA LangGraph orchestrator for frontend testing.
Implements the AG-UI Protocol v2.1.0 with proper event lifecycle.

Supports Demo Scenario 1: Inspecteur Koen - Restaurant Bella Rosa

Usage:
    python mock_server.py

Connects to: ws://localhost:8000/ws
"""

import asyncio
import json
import sys
import time
import uuid

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
    """Handle HTTP requests that aren't WebSocket upgrades."""
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return Response(200, "OK", websockets.Headers(), b"AG-UI Mock Server OK\n")
    return None


async def main():
    """Start the mock WebSocket server."""
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║     AG-UI Protocol Mock Server v2.1.0 - Demo Mode          ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print("║  Endpoint: ws://localhost:8000/ws                          ║")
    print("║  Press Ctrl+C to stop                                      ║")
    print("╚════════════════════════════════════════════════════════════╝")
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

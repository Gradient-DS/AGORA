#!/usr/bin/env python3
"""
Mock server for testing AG-UI Protocol WebSocket communication.

This server simulates the AGORA LangGraph orchestrator for frontend testing.

Usage:
    python mock_server.py

Connects to: ws://localhost:8765
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

import websockets


def now_iso() -> str:
    """Return current timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


async def handle_connection(websocket):
    """Handle incoming WebSocket connections."""
    print(f"[{now_iso()}] Client connected")

    try:
        async for message in websocket:
            data = json.loads(message)
            print(f"[{now_iso()}] Received: {json.dumps(data, indent=2)}")

            # Check if it's a custom event (approval response)
            if data.get("type") == "CUSTOM":
                name = data.get("name", "")
                if name == "agora:tool_approval_response":
                    await handle_approval_response(websocket, data)
                    continue

            # Otherwise treat as RunAgentInput
            if "threadId" in data:
                await handle_run_input(websocket, data)

    except websockets.exceptions.ConnectionClosed:
        print(f"[{now_iso()}] Client disconnected")


async def handle_run_input(websocket, data: dict):
    """Handle a RunAgentInput and simulate an agent response."""
    thread_id = data.get("threadId", str(uuid.uuid4()))
    run_id = data.get("runId", str(uuid.uuid4()))
    messages = data.get("messages", [])

    user_content = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break

    # Send RUN_STARTED
    await send_event(
        websocket,
        {
            "type": "RUN_STARTED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_iso(),
        },
    )

    # Send STEP_STARTED (routing)
    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "routing",
            "metadata": {"message": "Analyzing request..."},
            "timestamp": now_iso(),
        },
    )
    await asyncio.sleep(0.3)

    await send_event(
        websocket,
        {
            "type": "STEP_FINISHED",
            "stepName": "routing",
            "timestamp": now_iso(),
        },
    )

    # Send STEP_STARTED (thinking)
    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "thinking",
            "timestamp": now_iso(),
        },
    )
    await asyncio.sleep(0.2)

    # Check for tool approval trigger
    if "report" in user_content.lower() or "generate" in user_content.lower():
        await simulate_tool_approval_flow(websocket, thread_id)

    # Stream response
    message_id = f"msg-{uuid.uuid4()}"
    response_chunks = [
        "Based on ",
        "the information ",
        "you provided, ",
        "I can help you with your inspection. ",
        "Here is my response to your query.",
    ]

    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_START",
            "messageId": message_id,
            "role": "assistant",
            "timestamp": now_iso(),
        },
    )

    for chunk in response_chunks:
        await send_event(
            websocket,
            {
                "type": "TEXT_MESSAGE_CONTENT",
                "messageId": message_id,
                "delta": chunk,
                "timestamp": now_iso(),
            },
        )
        await asyncio.sleep(0.1)

    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_END",
            "messageId": message_id,
            "timestamp": now_iso(),
        },
    )

    await send_event(
        websocket,
        {
            "type": "STEP_FINISHED",
            "stepName": "thinking",
            "timestamp": now_iso(),
        },
    )

    await send_event(
        websocket,
        {
            "type": "RUN_FINISHED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_iso(),
        },
    )


async def simulate_tool_approval_flow(websocket, thread_id: str):
    """Simulate a tool approval request flow."""
    approval_id = f"appr-{uuid.uuid4()}"

    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "executing_tools",
            "metadata": {"tool": "generate_final_report"},
            "timestamp": now_iso(),
        },
    )

    await send_event(
        websocket,
        {
            "type": "CUSTOM",
            "name": "agora:tool_approval_request",
            "value": {
                "toolName": "generate_final_report",
                "toolDescription": "Generates an official inspection report PDF",
                "parameters": {"inspection_id": "INS-2024-MOCK"},
                "reasoning": "User requested to generate a report",
                "riskLevel": "high",
                "approvalId": approval_id,
            },
            "timestamp": now_iso(),
        },
    )

    print(f"[{now_iso()}] Waiting for approval response (id: {approval_id})")


async def handle_approval_response(websocket, data: dict):
    """Handle a tool approval response."""
    value = data.get("value", {})
    approval_id = value.get("approvalId", "")
    approved = value.get("approved", False)
    feedback = value.get("feedback", "")

    print(
        f"[{now_iso()}] Approval response: {approved} (id: {approval_id}, feedback: {feedback})"
    )

    if approved:
        tool_call_id = f"call-{uuid.uuid4()}"

        await send_event(
            websocket,
            {
                "type": "TOOL_CALL_START",
                "toolCallId": tool_call_id,
                "toolCallName": "generate_final_report",
                "timestamp": now_iso(),
            },
        )

        await send_event(
            websocket,
            {
                "type": "TOOL_CALL_ARGS",
                "toolCallId": tool_call_id,
                "delta": json.dumps({"inspection_id": "INS-2024-MOCK"}),
                "timestamp": now_iso(),
            },
        )

        await asyncio.sleep(0.5)

        await send_event(
            websocket,
            {
                "type": "TOOL_CALL_END",
                "toolCallId": tool_call_id,
                "result": "Report generated: report-INS-2024-MOCK.pdf",
                "timestamp": now_iso(),
            },
        )

    await send_event(
        websocket,
        {
            "type": "STEP_FINISHED",
            "stepName": "executing_tools",
            "timestamp": now_iso(),
        },
    )


async def send_event(websocket, event: dict):
    """Send an event over WebSocket."""
    event_json = json.dumps(event)
    print(f"[{now_iso()}] Sending: {event['type']}")
    await websocket.send(event_json)


async def main():
    """Start the mock WebSocket server."""
    print(f"[{now_iso()}] Starting AG-UI Mock Server on ws://localhost:8765")
    print("Use Ctrl+C to stop the server")
    print("-" * 60)

    async with websockets.serve(handle_connection, "localhost", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n[{now_iso()}] Server stopped")

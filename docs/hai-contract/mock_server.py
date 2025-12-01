#!/usr/bin/env python3
"""
Mock server for testing AG-UI Protocol WebSocket communication.

This server simulates the AGORA LangGraph orchestrator for frontend testing.
Implements the AG-UI Protocol v2.1.0 with proper event lifecycle.

Usage:
    python mock_server.py

Connects to: ws://localhost:8765
"""

import asyncio
import json
import time
import uuid

import websockets


def now_timestamp() -> int:
    """Return current timestamp as Unix milliseconds (AG-UI standard)."""
    return int(time.time() * 1000)


def log_event(direction: str, event_type: str) -> None:
    """Log an event with timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    arrow = "→" if direction == "send" else "←"
    print(f"[{timestamp}] {arrow} {event_type}")


async def send_event(websocket, event: dict) -> None:
    """Send an event over WebSocket and log it."""
    log_event("send", event.get("type", "unknown"))
    await websocket.send(json.dumps(event))


async def handle_connection(websocket):
    """Handle incoming WebSocket connections."""
    print(f"\n{'='*60}")
    print("Client connected")
    print(f"{'='*60}")

    try:
        async for message in websocket:
            data = json.loads(message)
            event_type = data.get("type", "RunAgentInput")
            log_event("recv", event_type)

            if data.get("type") == "CUSTOM":
                name = data.get("name", "")
                if name == "agora:tool_approval_response":
                    await handle_approval_response(websocket, data)
                    continue
                print(f"  Unknown custom event: {name}")
                continue

            if "threadId" in data or "thread_id" in data:
                await handle_run_input(websocket, data)

    except websockets.exceptions.ConnectionClosed:
        print("\nClient disconnected")
        print(f"{'='*60}\n")


async def handle_run_input(websocket, data: dict) -> None:
    """Handle a RunAgentInput and simulate an agent response."""
    thread_id = data.get("threadId") or data.get("thread_id") or str(uuid.uuid4())
    run_id = data.get("runId") or data.get("run_id") or str(uuid.uuid4())
    messages = data.get("messages", [])

    user_content = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break

    print(f"  User: {user_content[:50]}...")

    # RUN_STARTED
    await send_event(
        websocket,
        {
            "type": "RUN_STARTED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_timestamp(),
        },
    )

    # Initial STATE_SNAPSHOT
    await send_event(
        websocket,
        {
            "type": "STATE_SNAPSHOT",
            "snapshot": {
                "threadId": thread_id,
                "runId": run_id,
                "currentAgent": "general-agent",
                "status": "processing",
            },
            "timestamp": now_timestamp(),
        },
    )

    # STEP_STARTED (routing)
    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "routing",
            "timestamp": now_timestamp(),
        },
    )
    await asyncio.sleep(0.2)

    # STEP_FINISHED (routing)
    await send_event(
        websocket,
        {
            "type": "STEP_FINISHED",
            "stepName": "routing",
            "timestamp": now_timestamp(),
        },
    )

    # STEP_STARTED (thinking)
    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "thinking",
            "timestamp": now_timestamp(),
        },
    )
    await asyncio.sleep(0.1)

    # Check for tool approval trigger
    if "report" in user_content.lower() or "generate" in user_content.lower():
        # STEP_FINISHED (thinking) before tool execution
        await send_event(
            websocket,
            {
                "type": "STEP_FINISHED",
                "stepName": "thinking",
                "timestamp": now_timestamp(),
            },
        )
        await simulate_tool_approval_flow(websocket, thread_id, run_id)
        return  # Response will continue after approval

    # Stream response
    await stream_assistant_response(websocket, thread_id, run_id)


async def stream_assistant_response(
    websocket,
    thread_id: str,
    run_id: str,
    content_chunks: list[str] | None = None,
) -> None:
    """Stream an assistant response."""
    message_id = f"msg-{uuid.uuid4()}"

    if content_chunks is None:
        content_chunks = [
            "Based on ",
            "the information ",
            "you provided, ",
            "I can help you with your inspection. ",
            "Here is my response to your query.",
        ]

    # TEXT_MESSAGE_START
    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_START",
            "messageId": message_id,
            "role": "assistant",
            "timestamp": now_timestamp(),
        },
    )

    # TEXT_MESSAGE_CONTENT (streaming)
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
        await asyncio.sleep(0.05)

    # TEXT_MESSAGE_END
    await send_event(
        websocket,
        {
            "type": "TEXT_MESSAGE_END",
            "messageId": message_id,
            "timestamp": now_timestamp(),
        },
    )

    # STEP_FINISHED (thinking)
    await send_event(
        websocket,
        {
            "type": "STEP_FINISHED",
            "stepName": "thinking",
            "timestamp": now_timestamp(),
        },
    )

    # Final STATE_SNAPSHOT
    await send_event(
        websocket,
        {
            "type": "STATE_SNAPSHOT",
            "snapshot": {
                "threadId": thread_id,
                "runId": run_id,
                "currentAgent": "general-agent",
                "status": "completed",
            },
            "timestamp": now_timestamp(),
        },
    )

    # RUN_FINISHED
    await send_event(
        websocket,
        {
            "type": "RUN_FINISHED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_timestamp(),
        },
    )


async def simulate_tool_approval_flow(
    websocket,
    thread_id: str,
    run_id: str,
) -> None:
    """Simulate a tool approval request flow."""
    approval_id = f"appr-{uuid.uuid4()}"

    # Store context for later (in real impl, this would be in a dict)
    websocket._pending_approval = {
        "approval_id": approval_id,
        "thread_id": thread_id,
        "run_id": run_id,
    }

    # STEP_STARTED (executing_tools)
    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "executing_tools",
            "timestamp": now_timestamp(),
        },
    )

    # agora:tool_approval_request (CUSTOM event)
    await send_event(
        websocket,
        {
            "type": "CUSTOM",
            "name": "agora:tool_approval_request",
            "value": {
                "toolName": "generate_final_report",
                "toolDescription": "Generates an official inspection report PDF that will be stored permanently",
                "parameters": {
                    "inspectionId": "INS-2024-MOCK",
                    "includePhotos": True,
                    "language": "nl",
                },
                "reasoning": "User requested to generate a report",
                "riskLevel": "high",
                "approvalId": approval_id,
            },
            "timestamp": now_timestamp(),
        },
    )

    print(f"  ⏳ Waiting for approval (id: {approval_id[:12]}...)")


async def handle_approval_response(websocket, data: dict) -> None:
    """Handle a tool approval response."""
    value = data.get("value", {})
    approval_id = value.get("approvalId", "")
    approved = value.get("approved", False)
    feedback = value.get("feedback", "")

    # Get stored context
    pending = getattr(websocket, "_pending_approval", {})
    thread_id = pending.get("thread_id", str(uuid.uuid4()))
    run_id = pending.get("run_id", str(uuid.uuid4()))

    status = "✅ Approved" if approved else "❌ Rejected"
    print(f"  {status} (feedback: {feedback or 'none'})")

    if approved:
        await execute_approved_tool(websocket, thread_id, run_id)
    else:
        await handle_rejected_tool(websocket, thread_id, run_id)


async def execute_approved_tool(
    websocket,
    thread_id: str,
    run_id: str,
) -> None:
    """Execute a tool after approval."""
    tool_call_id = f"call-{uuid.uuid4()}"

    # TOOL_CALL_START
    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_START",
            "toolCallId": tool_call_id,
            "toolCallName": "generate_final_report",
            "parentMessageId": None,
            "timestamp": now_timestamp(),
        },
    )

    # TOOL_CALL_ARGS
    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_ARGS",
            "toolCallId": tool_call_id,
            "delta": json.dumps(
                {
                    "inspectionId": "INS-2024-MOCK",
                    "includePhotos": True,
                    "language": "nl",
                }
            ),
            "timestamp": now_timestamp(),
        },
    )

    await asyncio.sleep(0.3)

    # TOOL_CALL_END (signals end of argument streaming - no result field!)
    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_END",
            "toolCallId": tool_call_id,
            "timestamp": now_timestamp(),
        },
    )

    # TOOL_CALL_RESULT (contains the actual execution result)
    await send_event(
        websocket,
        {
            "type": "TOOL_CALL_RESULT",
            "messageId": f"tool-result-{tool_call_id}",
            "toolCallId": tool_call_id,
            "content": "Report generated successfully: report-INS-2024-MOCK.pdf",
            "role": "tool",
            "timestamp": now_timestamp(),
        },
    )

    # STEP_FINISHED (executing_tools)
    await send_event(
        websocket,
        {
            "type": "STEP_FINISHED",
            "stepName": "executing_tools",
            "timestamp": now_timestamp(),
        },
    )

    # STEP_STARTED (thinking) - back to thinking after tool
    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "thinking",
            "timestamp": now_timestamp(),
        },
    )

    # Stream follow-up response
    await stream_assistant_response(
        websocket,
        thread_id,
        run_id,
        content_chunks=[
            "I have successfully generated the inspection report ",
            "for INS-2024-MOCK. ",
            "You can download the PDF using the link provided.",
        ],
    )


async def handle_rejected_tool(
    websocket,
    thread_id: str,
    run_id: str,
) -> None:
    """Handle a rejected tool execution."""
    # STEP_FINISHED (executing_tools)
    await send_event(
        websocket,
        {
            "type": "STEP_FINISHED",
            "stepName": "executing_tools",
            "timestamp": now_timestamp(),
        },
    )

    # STEP_STARTED (thinking)
    await send_event(
        websocket,
        {
            "type": "STEP_STARTED",
            "stepName": "thinking",
            "timestamp": now_timestamp(),
        },
    )

    # Stream cancellation response
    await stream_assistant_response(
        websocket,
        thread_id,
        run_id,
        content_chunks=["I have cancelled the action as requested."],
    )


async def simulate_error_flow(websocket, thread_id: str, run_id: str) -> None:
    """Simulate an error during processing."""
    # RUN_ERROR (official AG-UI error event)
    await send_event(
        websocket,
        {
            "type": "RUN_ERROR",
            "message": "Error processing request: LLM rate limit exceeded",
            "code": "processing_error",
            "timestamp": now_timestamp(),
        },
    )

    # RUN_FINISHED (always sent, even after error)
    await send_event(
        websocket,
        {
            "type": "RUN_FINISHED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_timestamp(),
        },
    )


async def simulate_moderation_error(websocket, thread_id: str, run_id: str) -> None:
    """Simulate a moderation violation error."""
    # agora:error (AGORA-specific custom error)
    await send_event(
        websocket,
        {
            "type": "CUSTOM",
            "name": "agora:error",
            "value": {
                "errorCode": "moderation_violation",
                "message": "Your message contains prohibited content",
                "details": {
                    "reason": "content_policy_violation",
                    "category": "inappropriate_language",
                },
            },
            "timestamp": now_timestamp(),
        },
    )

    # RUN_FINISHED
    await send_event(
        websocket,
        {
            "type": "RUN_FINISHED",
            "threadId": thread_id,
            "runId": run_id,
            "timestamp": now_timestamp(),
        },
    )


async def main():
    """Start the mock WebSocket server."""
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║        AG-UI Protocol Mock Server v2.1.0                   ║")
    print("╠════════════════════════════════════════════════════════════╣")
    print("║  Endpoint: ws://localhost:8765                             ║")
    print("║  Press Ctrl+C to stop                                      ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print("Trigger keywords:")
    print("  • 'report' or 'generate' → Tool approval flow")
    print()

    async with websockets.serve(handle_connection, "localhost", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")

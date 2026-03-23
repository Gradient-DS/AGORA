#!/usr/bin/env python3
"""Test script to connect to the AGORA WebSocket and check for duplicate spoken messages.

Usage:
    python scripts/test_ws_spoken.py
    python scripts/test_ws_spoken.py --url ws://localhost:8000/ws
    python scripts/test_ws_spoken.py --message "Wat zijn de regels voor voedselveiligheid?"
"""

import argparse
import asyncio
import json
import time
import uuid
from collections import defaultdict

import websockets


async def test_ws(url: str, message: str) -> None:
    thread_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    user_id = "00000000-0000-0000-0000-000000000001"

    payload = {
        "threadId": thread_id,
        "runId": run_id,
        "userId": user_id,
        "messages": [{"role": "user", "content": message}],
    }

    print(f"Connecting to {url}...")
    print(f"Thread: {thread_id}")
    print(f"Message: {message}\n")

    # Track events
    spoken_starts: dict[str, int] = defaultdict(int)
    spoken_contents: dict[str, list[str]] = defaultdict(list)
    spoken_ends: dict[str, int] = defaultdict(int)
    text_message_starts: dict[str, int] = defaultdict(int)
    text_message_contents: dict[str, list[str]] = defaultdict(list)
    text_message_ends: dict[str, int] = defaultdict(int)
    all_events: list[dict] = []

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps(payload))
        t_start = time.perf_counter()
        print("Sent message, waiting for events...\n")
        print("-" * 60)

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                event = json.loads(raw)
                all_events.append(event)

                event_type = event.get("type", "")
                event_name = event.get("name", "")

                # Track text messages
                if event_type == "TEXT_MESSAGE_START":
                    msg_id = event.get("messageId", "unknown")
                    text_message_starts[msg_id] += 1
                    print(f"  TEXT_MESSAGE_START  id={msg_id}")

                elif event_type == "TEXT_MESSAGE_CONTENT":
                    msg_id = event.get("messageId", "unknown")
                    delta = event.get("delta", "")
                    text_message_contents[msg_id].append(delta)

                elif event_type == "TEXT_MESSAGE_END":
                    msg_id = event.get("messageId", "unknown")
                    text_message_ends[msg_id] += 1
                    full_text = "".join(text_message_contents.get(msg_id, []))
                    print(f"  TEXT_MESSAGE_END    id={msg_id}")
                    print(f"    Written text ({len(full_text)} chars): {full_text[:150]}...")

                # Track spoken messages
                elif event_name == "agora:spoken_text_start":
                    msg_id = event.get("value", {}).get("messageId", "unknown")
                    spoken_starts[msg_id] += 1
                    print(f"  SPOKEN_TEXT_START   id={msg_id}")

                elif event_name == "agora:spoken_text_content":
                    msg_id = event.get("value", {}).get("messageId", "unknown")
                    delta = event.get("value", {}).get("delta", "")
                    spoken_contents[msg_id].append(delta)

                elif event_name == "agora:spoken_text_end":
                    msg_id = event.get("value", {}).get("messageId", "unknown")
                    spoken_ends[msg_id] += 1
                    full_spoken = "".join(spoken_contents.get(msg_id, []))
                    print(f"  SPOKEN_TEXT_END     id={msg_id}")
                    print(f"    Spoken text ({len(full_spoken)} chars): {full_spoken[:150]}...")

                # Lifecycle events
                elif event_type == "RUN_STARTED":
                    print(f"  RUN_STARTED")
                elif event_type == "RUN_FINISHED":
                    print(f"  RUN_FINISHED")
                    break
                elif event_type == "RUN_ERROR":
                    print(f"  RUN_ERROR: {event.get('message', 'unknown error')}")
                    break
                elif event_type == "STEP_STARTED":
                    step_name = event.get("stepName", "?")
                    print(f"  STEP_STARTED       step={step_name}")
                elif event_type == "STEP_FINISHED":
                    step_name = event.get("stepName", "?")
                    print(f"  STEP_FINISHED      step={step_name}")
                elif event_type == "TOOL_CALL_START":
                    tool_name = event.get("toolCallName", "?")
                    print(f"  TOOL_CALL_START    tool={tool_name}")
                elif event_type == "TOOL_CALL_END":
                    tool_name = event.get("toolCallName", "?")
                    print(f"  TOOL_CALL_END      tool={tool_name}")

            except asyncio.TimeoutError:
                print("\nTimeout waiting for events (60s)")
                break

    # Summary
    t_end = time.perf_counter()
    elapsed = t_end - t_start

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\nTotal time: {elapsed:.2f}s")
    print(f"Total events received: {len(all_events)}")

    print(f"\nText messages:")
    for msg_id in text_message_starts:
        starts = text_message_starts[msg_id]
        ends = text_message_ends.get(msg_id, 0)
        chunks = len(text_message_contents.get(msg_id, []))
        print(f"  {msg_id}: starts={starts}, content_chunks={chunks}, ends={ends}")

    print(f"\nSpoken messages:")
    for msg_id in spoken_starts:
        starts = spoken_starts[msg_id]
        ends = spoken_ends.get(msg_id, 0)
        chunks = len(spoken_contents.get(msg_id, []))
        print(f"  {msg_id}: starts={starts}, content_chunks={chunks}, ends={ends}")

    # Check for duplicates
    print("\n" + "-" * 60)
    has_issue = False

    for msg_id in spoken_starts:
        if spoken_starts[msg_id] > 1:
            print(f"BUG: spoken_text_start sent {spoken_starts[msg_id]}x for {msg_id}")
            has_issue = True
        if spoken_ends.get(msg_id, 0) > 1:
            print(f"BUG: spoken_text_end sent {spoken_ends[msg_id]}x for {msg_id}")
            has_issue = True

    if len(spoken_starts) > len(text_message_starts):
        print(f"WARNING: More spoken streams ({len(spoken_starts)}) than text messages ({len(text_message_starts)})")
        has_issue = True

    if not has_issue:
        print("OK: No duplicate spoken messages detected")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test AGORA WebSocket for duplicate spoken messages")
    parser.add_argument("--url", default="ws://localhost:8000/ws", help="WebSocket URL")
    parser.add_argument("--message", default="Hallo, wat kun je voor me doen?", help="Message to send")
    args = parser.parse_args()

    asyncio.run(test_ws(args.url, args.message))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
AGORA API Test Script

Tests the production API endpoints including:
- HTTP health checks and authentication
- WebSocket streaming
- All backend routes (langgraph, openai, mock)

Usage:
    python scripts/test_api.py --api-key YOUR_API_KEY
    python scripts/test_api.py --api-key YOUR_API_KEY --base-url https://your-domain.com

Requirements:
    pip install websockets httpx
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing httpx. Install with: pip install httpx")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Missing websockets. Install with: pip install websockets")
    sys.exit(1)


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    duration_ms: float


class APITester:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.ws_url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        self.results: list[TestResult] = []

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    async def run_all_tests(self) -> bool:
        """Run all tests and return True if all passed."""
        print(f"\n{'='*60}")
        print(f"AGORA API Test Suite")
        print(f"{'='*60}")
        print(f"Base URL: {self.base_url}")
        print(f"API Key:  {self.api_key[:8]}...{self.api_key[-4:]}")
        print(f"{'='*60}\n")

        # HTTP Tests
        print("HTTP Endpoint Tests")
        print("-" * 40)
        await self.test_health_no_auth()
        await self.test_health_with_auth()
        await self.test_health_wrong_key()
        await self.test_gateway_backends()
        await self.test_agents_endpoint()
        await self.test_backend_health("langgraph")
        await self.test_backend_health("openai")
        await self.test_backend_health("mock")

        # WebSocket Tests
        print("\nWebSocket Streaming Tests")
        print("-" * 40)
        await self.test_websocket_no_auth()
        await self.test_websocket_wrong_key()
        await self.test_websocket_streaming()
        await self.test_websocket_backend_route("langgraph")

        # Print Summary
        self._print_summary()

        return all(r.passed for r in self.results)

    def _record(self, name: str, passed: bool, message: str, duration_ms: float):
        result = TestResult(name, passed, message, duration_ms)
        self.results.append(result)
        status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
        print(f"  [{status}] {name}: {message} ({duration_ms:.0f}ms)")

    async def test_health_no_auth(self):
        """Test that health endpoint requires auth."""
        start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/langgraph/health")
                duration = (time.time() - start) * 1000
                if resp.status_code == 401:
                    self._record("Health (no auth)", True, "Returns 401 as expected", duration)
                else:
                    self._record("Health (no auth)", False, f"Expected 401, got {resp.status_code}", duration)
        except Exception as e:
            self._record("Health (no auth)", False, str(e), (time.time() - start) * 1000)

    async def test_health_with_auth(self):
        """Test health endpoint with valid auth."""
        start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/api/langgraph/health",
                    headers=self._headers()
                )
                duration = (time.time() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    self._record("Health (with auth)", True, f"status={data.get('status')}", duration)
                else:
                    self._record("Health (with auth)", False, f"Status {resp.status_code}", duration)
        except Exception as e:
            self._record("Health (with auth)", False, str(e), (time.time() - start) * 1000)

    async def test_health_wrong_key(self):
        """Test health endpoint with wrong API key."""
        start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/api/langgraph/health",
                    headers={"X-API-Key": "wrong-key"}
                )
                duration = (time.time() - start) * 1000
                if resp.status_code == 401:
                    self._record("Health (wrong key)", True, "Returns 401 as expected", duration)
                else:
                    self._record("Health (wrong key)", False, f"Expected 401, got {resp.status_code}", duration)
        except Exception as e:
            self._record("Health (wrong key)", False, str(e), (time.time() - start) * 1000)

    async def test_gateway_backends(self):
        """Test gateway backends listing."""
        start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/gateway/backends",
                    headers=self._headers()
                )
                duration = (time.time() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    backends = data.get("backends", [])
                    self._record("Gateway backends", True, f"Found: {backends}", duration)
                else:
                    self._record("Gateway backends", False, f"Status {resp.status_code}", duration)
        except Exception as e:
            self._record("Gateway backends", False, str(e), (time.time() - start) * 1000)

    async def test_agents_endpoint(self):
        """Test agents listing endpoint."""
        start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/agents",
                    headers=self._headers()
                )
                duration = (time.time() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    agents = data.get("agents", [])
                    self._record("Agents endpoint", True, f"Found {len(agents)} agents", duration)
                else:
                    self._record("Agents endpoint", False, f"Status {resp.status_code}", duration)
        except Exception as e:
            self._record("Agents endpoint", False, str(e), (time.time() - start) * 1000)

    async def test_backend_health(self, backend: str):
        """Test specific backend health endpoint."""
        start = time.time()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/api/{backend}/health",
                    headers=self._headers()
                )
                duration = (time.time() - start) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    service = data.get("service", "unknown")
                    self._record(f"Backend: {backend}", True, f"service={service}", duration)
                else:
                    self._record(f"Backend: {backend}", False, f"Status {resp.status_code}", duration)
        except Exception as e:
            self._record(f"Backend: {backend}", False, str(e), (time.time() - start) * 1000)

    async def test_websocket_no_auth(self):
        """Test WebSocket connection without auth."""
        start = time.time()
        try:
            async with websockets.connect(f"{self.ws_url}/ws", close_timeout=5) as ws:
                # Should be closed by server
                await asyncio.wait_for(ws.recv(), timeout=5)
                self._record("WebSocket (no auth)", False, "Should have been rejected", (time.time() - start) * 1000)
        except websockets.exceptions.ConnectionClosed as e:
            duration = (time.time() - start) * 1000
            if e.code == 4001:
                self._record("WebSocket (no auth)", True, "Rejected with 4001 as expected", duration)
            else:
                self._record("WebSocket (no auth)", True, f"Rejected with code {e.code}", duration)
        except websockets.exceptions.InvalidStatusCode as e:
            # HTTP rejection before WebSocket upgrade (401/403) is also valid
            duration = (time.time() - start) * 1000
            if e.status_code in (401, 403):
                self._record("WebSocket (no auth)", True, f"Rejected with HTTP {e.status_code}", duration)
            else:
                self._record("WebSocket (no auth)", False, f"Unexpected HTTP {e.status_code}", duration)
        except Exception as e:
            # Handle "server rejected WebSocket connection: HTTP 403" style errors
            duration = (time.time() - start) * 1000
            err_str = str(e)
            if "HTTP 401" in err_str or "HTTP 403" in err_str:
                self._record("WebSocket (no auth)", True, f"Rejected: {err_str}", duration)
            else:
                self._record("WebSocket (no auth)", False, err_str, duration)

    async def test_websocket_wrong_key(self):
        """Test WebSocket connection with wrong key."""
        start = time.time()
        try:
            async with websockets.connect(f"{self.ws_url}/ws?token=wrong-key", close_timeout=5) as ws:
                await asyncio.wait_for(ws.recv(), timeout=5)
                self._record("WebSocket (wrong key)", False, "Should have been rejected", (time.time() - start) * 1000)
        except websockets.exceptions.ConnectionClosed as e:
            duration = (time.time() - start) * 1000
            self._record("WebSocket (wrong key)", True, f"Rejected with code {e.code}", duration)
        except websockets.exceptions.InvalidStatusCode as e:
            # HTTP rejection before WebSocket upgrade (401/403) is also valid
            duration = (time.time() - start) * 1000
            if e.status_code in (401, 403):
                self._record("WebSocket (wrong key)", True, f"Rejected with HTTP {e.status_code}", duration)
            else:
                self._record("WebSocket (wrong key)", False, f"Unexpected HTTP {e.status_code}", duration)
        except Exception as e:
            # Handle "server rejected WebSocket connection: HTTP 403" style errors
            duration = (time.time() - start) * 1000
            err_str = str(e)
            if "HTTP 401" in err_str or "HTTP 403" in err_str:
                self._record("WebSocket (wrong key)", True, f"Rejected: {err_str}", duration)
            else:
                self._record("WebSocket (wrong key)", False, err_str, duration)

    async def test_websocket_streaming(self):
        """Test WebSocket streaming with a real message."""
        start = time.time()
        try:
            url = f"{self.ws_url}/ws?token={self.api_key}"
            async with websockets.connect(url, close_timeout=30) as ws:
                # Send a simple message
                request = {
                    "threadId": str(uuid.uuid4()),
                    "runId": str(uuid.uuid4()),
                    "userId": str(uuid.uuid4()),
                    "messages": [{"role": "user", "content": "Say 'test successful' and nothing else."}]
                }
                await ws.send(json.dumps(request))

                # Collect events
                events = []
                text_content = ""

                async for msg in ws:
                    event = json.loads(msg)
                    events.append(event)
                    event_type = event.get("type", "")

                    if event_type == "TEXT_MESSAGE_CONTENT":
                        text_content += event.get("delta", "")
                    elif event_type == "RUN_FINISHED":
                        break
                    elif event_type == "RUN_ERROR":
                        raise Exception(f"Run error: {event.get('message')}")

                    if len(events) > 500:
                        break

                duration = (time.time() - start) * 1000
                self._record(
                    "WebSocket streaming",
                    True,
                    f"{len(events)} events, {len(text_content)} chars",
                    duration
                )

                # Print sample of response
                if text_content:
                    preview = text_content[:100] + "..." if len(text_content) > 100 else text_content
                    print(f"      Response preview: {preview}")

        except Exception as e:
            self._record("WebSocket streaming", False, str(e), (time.time() - start) * 1000)

    async def test_websocket_backend_route(self, backend: str):
        """Test WebSocket via specific backend route."""
        start = time.time()
        try:
            url = f"{self.ws_url}/api/{backend}/ws?token={self.api_key}"
            async with websockets.connect(url, close_timeout=30) as ws:
                request = {
                    "threadId": str(uuid.uuid4()),
                    "runId": str(uuid.uuid4()),
                    "userId": str(uuid.uuid4()),
                    "messages": [{"role": "user", "content": "Reply with just: OK"}]
                }
                await ws.send(json.dumps(request))

                events = []
                async for msg in ws:
                    event = json.loads(msg)
                    events.append(event)
                    if event.get("type") in ["RUN_FINISHED", "RUN_ERROR"]:
                        break
                    if len(events) > 200:
                        break

                duration = (time.time() - start) * 1000
                self._record(f"WebSocket /{backend}/ws", True, f"{len(events)} events", duration)

        except Exception as e:
            self._record(f"WebSocket /{backend}/ws", False, str(e), (time.time() - start) * 1000)

    def _print_summary(self):
        """Print test summary."""
        print(f"\n{'='*60}")
        print("Test Summary")
        print(f"{'='*60}")

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print(f"Passed: {passed}/{total}")
        print(f"Failed: {failed}/{total}")

        if failed > 0:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

        print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Test AGORA API endpoints")
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument(
        "--base-url",
        default="https://agora.gradient-testing.nl",
        help="Base URL for the API (default: https://agora.gradient-testing.nl)"
    )
    args = parser.parse_args()

    tester = APITester(args.base_url, args.api_key)
    success = asyncio.run(tester.run_all_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

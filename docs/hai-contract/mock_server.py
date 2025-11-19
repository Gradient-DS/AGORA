import asyncio
import json
import logging
import uuid
import websockets
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MockServer")

class HAIMockServer:
    def __init__(self, host: str = "localhost", port: int = 8000):
        self.host = host
        self.port = port

    async def handle_connection(self, websocket):
        """Handle individual WebSocket connection."""
        client_id = str(uuid.uuid4())[:8]
        logger.info(f"Client connected: {client_id}")

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.process_message(websocket, data, client_id)
                except json.JSONDecodeError:
                    logger.error(f"[{client_id}] Invalid JSON received")
                    await self.send_error(websocket, "invalid_json", "Message was not valid JSON")
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {client_id}")

    async def process_message(self, websocket, data: Dict[str, Any], client_id: str):
        """Process incoming HAI protocol messages."""
        msg_type = data.get("type")
        session_id = data.get("session_id", "unknown-session")
        
        logger.info(f"[{client_id}] Received: {msg_type}")

        if msg_type == "user_message":
            content = data.get("content", "").lower()
            
            # 1. Acknowledge receipt (Thinking status)
            await self.send_status(websocket, "thinking", "Processing your request...", session_id)
            await asyncio.sleep(0.5) # Simulate network delay

            # SCENARIO: User asks for inspection report (triggers Approval Flow)
            if "report" in content or "rapport" in content:
                await self.handle_approval_scenario(websocket, session_id)
            
            # SCENARIO: User asks for search (triggers Tool Execution)
            elif "search" in content or "zoek" in content:
                await self.handle_tool_execution_scenario(websocket, session_id)
            
            # SCENARIO: Regular chat
            else:
                await self.handle_basic_chat(websocket, session_id)

        elif msg_type == "tool_approval_response":
            await self.handle_approval_response(websocket, data, session_id)

    async def handle_basic_chat(self, websocket, session_id: str):
        """Simulate a basic streaming response."""
        response_text = "Dit is een antwoord van de Mock Server. Ik simuleer de AGORA orchestrator."
        message_id = str(uuid.uuid4())

        # Stream response in chunks
        words = response_text.split(" ")
        for i, word in enumerate(words):
            is_final = (i == len(words) - 1)
            chunk = {
                "type": "assistant_message_chunk",
                "content": word + (" " if not is_final else ""),
                "session_id": session_id,
                "message_id": message_id,
                "is_final": is_final
            }
            await websocket.send(json.dumps(chunk))
            await asyncio.sleep(0.1) # Simulate typing speed
        
        await self.send_status(websocket, "completed", None, session_id)

    async def handle_tool_execution_scenario(self, websocket, session_id: str):
        """Simulate searching for regulations."""
        # 1. Routing
        await self.send_status(websocket, "routing", "Routing to Regulation Specialist...", session_id)
        await asyncio.sleep(0.8)

        # 2. Tool Start
        tool_call_id = f"call_{str(uuid.uuid4())[:8]}"
        await websocket.send(json.dumps({
            "type": "tool_call_start",
            "tool_call_id": tool_call_id,
            "tool_name": "search_regulations",
            "parameters": {"query": "food safety requirements", "limit": 5},
            "session_id": session_id,
            "agent_id": "regulation_agent"
        }))
        
        await self.send_status(websocket, "executing_tools", "Searching regulations...", session_id)
        await asyncio.sleep(1.5) # Simulate database latency

        # 3. Tool End
        await websocket.send(json.dumps({
            "type": "tool_call_end",
            "tool_call_id": tool_call_id,
            "tool_name": "search_regulations",
            "result": "Found 3 relevant articles: 1. Hygiene Code... 2. Temperature...",
            "session_id": session_id,
            "agent_id": "regulation_agent"
        }))

        # 4. Final Answer
        await self.handle_basic_chat(websocket, session_id)

    async def handle_approval_scenario(self, websocket, session_id: str):
        """Simulate a Human-in-the-Loop approval request."""
        approval_id = f"appr_{str(uuid.uuid4())[:8]}"
        
        await websocket.send(json.dumps({
            "type": "tool_approval_request",
            "tool_name": "generate_final_report",
            "tool_description": "Genereert het officiële inspectierapport (PDF) en slaat dit op.",
            "parameters": {"format": "pdf", "include_evidence": True},
            "reasoning": "U heeft gevraagd de inspectie af te ronden. Hiervoor moet het rapport worden gegenereerd.",
            "risk_level": "high",
            "session_id": session_id,
            "approval_id": approval_id
        }))
        
        logger.info(f"Sent approval request: {approval_id}")

    async def handle_approval_response(self, websocket, data: Dict[str, Any], session_id: str):
        """Handle the user's decision."""
        approved = data.get("approved", False)
        
        if approved:
            await websocket.send(json.dumps({
                "type": "assistant_message",
                "content": "Bedankt voor de goedkeuring. Ik ga het rapport nu genereren.",
                "session_id": session_id
            }))
            # Here you could simulate the tool execution sequence
        else:
            await websocket.send(json.dumps({
                "type": "assistant_message",
                "content": "Begrepen, ik annuleer de actie. Wat wilt u nu doen?",
                "session_id": session_id
            }))
        
        await self.send_status(websocket, "completed", None, session_id)

    async def send_status(self, websocket, status: str, message: str, session_id: str):
        await websocket.send(json.dumps({
            "type": "status",
            "status": status,
            "message": message,
            "session_id": session_id
        }))

    async def send_error(self, websocket, code: str, message: str):
        await websocket.send(json.dumps({
            "type": "error",
            "error_code": code,
            "message": message
        }))

    def run(self):
        """Start the WebSocket server."""
        start_server = websockets.serve(self.handle_connection, self.host, self.port)
        logger.info(f"Mock Server running on ws://{self.host}:{self.port}/ws")
        logger.info("Press Ctrl+C to stop")
        
        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
    try:
        # Check dependencies
        import websockets
    except ImportError:
        print("Error: 'websockets' library not found.")
        print("Run: pip install websockets")
        exit(1)

    server = HAIMockServer()
    server.run()


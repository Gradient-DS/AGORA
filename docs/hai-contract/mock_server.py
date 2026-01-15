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
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


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


# ---------------------------------------------------------------------------
# REQUEST MODELS (for FastAPI)
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    """Request body for creating a user."""

    email: str = Field(..., description="User's email address")
    name: str = Field(..., description="User's display name")


class UpdateUserRequest(BaseModel):
    """Request body for updating a user."""

    name: str | None = Field(None, description="User's display name")
    preferences: dict | None = Field(None, description="User preferences")


class UpdatePreferencesRequest(BaseModel):
    """Request body for updating user preferences."""

    theme: str | None = Field(None, description="UI theme: 'light', 'dark', or 'system'")
    notifications_enabled: bool | None = Field(None, description="Enable notifications")
    default_agent_id: str | None = Field(None, description="Default agent ID")
    language: str | None = Field(None, description="UI language (e.g., 'nl-NL')")
    spoken_text_type: str | None = Field(
        None,
        description="Spoken text type: 'dictate' or 'summarize'"
    )


class UpdateSessionRequest(BaseModel):
    """Request body for updating session metadata."""

    title: str | None = Field(None, description="New session title")


# ---------------------------------------------------------------------------
# FASTAPI APPLICATION
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    print()
    print("=" * 64)
    print("  AG-UI Protocol Mock Server v2.4.0 - Demo Mode (FastAPI)")
    print("=" * 64)
    print()
    print("  WebSocket: ws://localhost:8000/ws")
    print("  REST API:  http://localhost:8000")
    print("  API Docs:  http://localhost:8000/docs")
    print()
    yield
    print("\nServer shutting down...")


app = FastAPI(
    title="AGORA Mock Server (AG-UI Protocol)",
    description="Mock server for testing AG-UI Protocol WebSocket and REST API",
    version="2.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST ENDPOINTS
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "agora-mock", "protocol": "ag-ui"}


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "AGORA Mock Server",
        "version": "2.4.0",
        "protocol": "AG-UI Protocol v2.4.0",
        "endpoints": {
            "websocket": "/ws",
            "sessions": "/sessions?user_id={user_id}",
            "history": "/sessions/{id}/history?include_tools=true",
            "users": "/users",
            "currentUser": "/users/me",
            "agents": "/agents",
        },
    }


@app.get("/agents")
async def list_agents():
    """List available agents."""
    log_event("send", "HTTP", "GET /agents -> 4 agents")
    return {
        "success": True,
        "agents": [
            {"id": Agents.GENERAL, "name": "Algemene Assistent", "description": "Algemene vraag- en routeringagent"},
            {"id": Agents.HISTORY, "name": "Bedrijfsinformatie Specialist", "description": "KVK-gegevens en inspectiehistorie"},
            {"id": Agents.REGULATION, "name": "Regelgeving Specialist", "description": "Wet- en regelgevingsanalyse"},
            {"id": Agents.REPORTING, "name": "Rapportage Specialist", "description": "Inspectierapport genereren"},
        ],
    }


# ---------------------------------------------------------------------------
# SESSION ENDPOINTS
# ---------------------------------------------------------------------------


@app.get("/sessions")
async def list_sessions(user_id: str = Query(..., description="User/inspector persona ID")):
    """List all sessions for a user, ordered by last activity."""
    # Map UUID to legacy userId if needed (sessions use legacy IDs like "koen", "fatima")
    legacy_id = None
    for legacy, uuid_id in USER_ID_MAP.items():
        if uuid_id == user_id:
            legacy_id = legacy
            break
    # Match on both UUID and legacy ID
    user_sessions = [
        s for s in MOCK_SESSIONS.values()
        if s["userId"] == user_id or s["userId"] == legacy_id
    ]
    user_sessions.sort(key=lambda s: s["lastActivity"], reverse=True)
    log_event("send", "HTTP", f"GET /sessions?user_id={user_id} -> {len(user_sessions)} sessions")
    return {"success": True, "sessions": user_sessions, "totalCount": len(user_sessions)}


@app.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    include_tools: bool = Query(False, description="Include tool call messages"),
):
    """Get conversation history for a session."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    history = get_mock_history(session_id, include_tools)
    log_event("send", "HTTP", f"GET /sessions/{session_id}/history -> {len(history)} messages")
    return {"success": True, "threadId": session_id, "history": history, "messageCount": len(history)}


@app.get("/sessions/{session_id}/metadata")
async def get_session_metadata(session_id: str):
    """Get session metadata by ID."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    log_event("send", "HTTP", f"GET /sessions/{session_id}/metadata")
    return {"success": True, "session": MOCK_SESSIONS[session_id]}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    del MOCK_SESSIONS[session_id]
    log_event("send", "HTTP", f"DELETE /sessions/{session_id}")
    return {"success": True, "message": "Session deleted"}


@app.put("/sessions/{session_id}")
async def update_session(session_id: str, request: UpdateSessionRequest):
    """Update session metadata (e.g., rename)."""
    if session_id not in MOCK_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.title is not None:
        MOCK_SESSIONS[session_id]["title"] = request.title.strip()[:200]
        MOCK_SESSIONS[session_id]["lastActivity"] = datetime.now().isoformat() + "Z"

    log_event("send", "HTTP", f"PUT /sessions/{session_id}")
    return {"success": True, "session": MOCK_SESSIONS[session_id]}


# ---------------------------------------------------------------------------
# USER ENDPOINTS
# ---------------------------------------------------------------------------


@app.get("/users/me")
async def get_current_user():
    """Get current user profile."""
    if CURRENT_USER_ID not in MOCK_USERS:
        raise HTTPException(status_code=401, detail="User not found")
    user = MOCK_USERS[CURRENT_USER_ID]
    log_event("send", "HTTP", f"GET /users/me -> {user['name']}")
    return user


@app.get("/users/me/preferences")
async def get_current_user_preferences(
    user_id: str = Query(..., description="Current user ID")
):
    """Get current user's preferences."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")
    user = MOCK_USERS[user_id]
    default_preferences = {
        "theme": "system",
        "notifications_enabled": True,
        "default_agent_id": "general-agent",
        "language": "nl-NL",
        "spoken_text_type": "summarize",
    }
    preferences = user.get("preferences", default_preferences)
    log_event("send", "HTTP", f"GET /users/me/preferences?user_id={user_id}")
    return {"success": True, "preferences": preferences}


@app.put("/users/me/preferences")
async def update_current_user_preferences(
    request: UpdatePreferencesRequest,
    user_id: str = Query(..., description="Current user ID")
):
    """Update current user's preferences."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")
    user = MOCK_USERS[user_id]
    if "preferences" not in user:
        user["preferences"] = {
            "theme": "system",
            "notifications_enabled": True,
            "default_agent_id": "general-agent",
            "language": "nl-NL",
            "spoken_text_type": "summarize",
        }
    if request.theme is not None:
        if request.theme not in ("light", "dark", "system"):
            raise HTTPException(
                status_code=400,
                detail="theme must be 'light', 'dark', or 'system'"
            )
        user["preferences"]["theme"] = request.theme
    if request.notifications_enabled is not None:
        user["preferences"]["notifications_enabled"] = request.notifications_enabled
    if request.default_agent_id is not None:
        user["preferences"]["default_agent_id"] = request.default_agent_id
    if request.language is not None:
        user["preferences"]["language"] = request.language
    if request.spoken_text_type is not None:
        if request.spoken_text_type not in ("dictate", "summarize"):
            raise HTTPException(
                status_code=400,
                detail="spoken_text_type must be 'dictate' or 'summarize'"
            )
        user["preferences"]["spoken_text_type"] = request.spoken_text_type
    log_event("send", "HTTP", f"PUT /users/me/preferences?user_id={user_id}")
    return {"success": True, "preferences": user["preferences"]}


@app.post("/users", status_code=201)
async def create_user(request: CreateUserRequest):
    """Create a new user."""
    for existing_user in MOCK_USERS.values():
        if existing_user["email"] == request.email:
            raise HTTPException(status_code=409, detail="Email already exists")
    new_user_id = str(uuid.uuid4())
    now = datetime.now()
    new_user = {
        "id": new_user_id,
        "email": request.email,
        "name": request.name,
        "preferences": {
            "theme": "system",
            "notifications_enabled": True,
            "default_agent_id": "general-agent",
            "language": "nl-NL",
            "spoken_text_type": "summarize",
        },
        "createdAt": now.isoformat() + "Z",
        "lastActivity": now.isoformat() + "Z",
    }
    MOCK_USERS[new_user_id] = new_user
    log_event("send", "HTTP", f"POST /users -> created {new_user['email']}")
    return {"success": True, "user": new_user}


@app.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=100, description="Max users to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List all users, ordered by creation date."""
    all_users = list(MOCK_USERS.values())
    all_users.sort(key=lambda u: u["createdAt"], reverse=True)
    paginated_users = all_users[offset : offset + limit]
    log_event("send", "HTTP", f"GET /users -> {len(paginated_users)} of {len(all_users)} users")
    return {"success": True, "users": paginated_users, "totalCount": len(all_users)}


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user profile by ID."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")
    log_event("send", "HTTP", f"GET /users/{user_id}")
    return {"success": True, "user": MOCK_USERS[user_id]}


@app.put("/users/{user_id}")
async def update_user(user_id: str, request: UpdateUserRequest):
    """Update user profile."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")
    user = MOCK_USERS[user_id]
    if request.name is not None:
        user["name"] = request.name
    if request.preferences is not None:
        if "preferences" not in user:
            user["preferences"] = {}
        for key in ["theme", "notifications_enabled", "default_agent_id", "language"]:
            if key in request.preferences:
                user["preferences"][key] = request.preferences[key]
    log_event("send", "HTTP", f"PUT /users/{user_id}")
    return {"success": True, "user": user}


@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """Delete a user and associated sessions."""
    if user_id not in MOCK_USERS:
        raise HTTPException(status_code=404, detail="User not found")
    legacy_user_id = None
    for legacy_id, uuid_id in USER_ID_MAP.items():
        if uuid_id == user_id:
            legacy_user_id = legacy_id
            break
    sessions_to_delete = [
        sid for sid, s in MOCK_SESSIONS.items()
        if s["userId"] == legacy_user_id or s["userId"] == user_id
    ]
    for sid in sessions_to_delete:
        del MOCK_SESSIONS[sid]
    del MOCK_USERS[user_id]
    log_event("send", "HTTP", f"DELETE /users/{user_id} -> {len(sessions_to_delete)} sessions deleted")
    return {"success": True, "message": "User and associated sessions deleted", "deletedSessionsCount": len(sessions_to_delete)}


# ---------------------------------------------------------------------------
# MOCK DOCUMENTS (for report download testing)
# ---------------------------------------------------------------------------


@app.get("/mock_documents/{filename}")
async def get_mock_document(filename: str):
    """Serve mock document files (report.json, report.pdf)."""
    allowed_files = {"report.json", "report.pdf"}
    if filename not in allowed_files:
        raise HTTPException(status_code=404, detail="File not found")
    mock_docs_dir = Path(__file__).parent / "mock_documents"
    file_path = mock_docs_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    media_type = "application/json" if filename.endswith(".json") else "application/pdf"
    log_event("send", "HTTP", f"GET /mock_documents/{filename}")
    return FileResponse(path=file_path, media_type=media_type, filename=filename)


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
    text = text.replace("KVK", "Kamer van Koophandel")
    text = text.replace("NVWA", "Nederlandse Voedsel- en Warenautoriteit")
    text = text.replace("°C", " graden Celsius")
    text = text.replace("EU", "Europese Unie")
    text = text.replace("PDF", "P D F")
    text = text.replace("ID", "I D")

    return text.strip()


def log_event(direction: str, event_type: str, detail: str = "") -> None:
    """Log an event with timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    arrow = "→" if direction == "send" else "←"
    suffix = f" ({detail})" if detail else ""
    print(f"[{timestamp}] {arrow} {event_type}{suffix}")


async def send_event(websocket: WebSocket, event: dict, detail: str = "") -> None:
    """Send an event over WebSocket and log it."""
    log_event("send", event.get("type", "unknown"), detail)
    await websocket.send_text(json.dumps(event))


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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for AG-UI protocol communication."""
    await websocket.accept()

    state = ConversationState()

    try:
        while True:
            try:
                raw_message = await websocket.receive_text()
                data = json.loads(raw_message)
                event_type = data.get("type", "RunAgentInput")
                log_event("recv", event_type)

                if data.get("type") == "CUSTOM":
                    name = data.get("name", "")
                    if name == "agora:tool_approval_response":
                        await handle_approval_response(websocket, data, state)
                        continue
                    continue

                if "threadId" in data or "thread_id" in data:
                    await handle_run_input(websocket, data, state)

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                continue

    except Exception:
        pass


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

    for chunk in content_chunks:
        # Send regular text chunk
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


def main():
    """Start the mock server."""
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
    print("    GET  /users/me/preferences             - Get preferences")
    print("    PUT  /users/me/preferences             - Update preferences")
    print("    POST /users                            - Create new user")
    print("    GET  /users                            - List all users")
    print("    GET  /users/{id}                       - Get user by ID")
    print("    PUT  /users/{id}                       - Update user")
    print("    DELETE /users/{id}                     - Delete user")
    print()
    print("Mock Data (for testing):")
    print("  Sessions: koen (2), fatima (1), jan (1)")
    print("  Users: Koen, Fatima, Jan")
    print()
    print("Test the REST API:")
    print("  curl http://localhost:8000/sessions?user_id=koen")
    print("  curl http://localhost:8000/users/me")
    print()
    print("-" * 64)
    print()
    print(f"Demo Scenario: Inspecteur Koen - Restaurant Bella Rosa")
    print()
    print("Agents:")
    print(f"  - {Agents.GENERAL}")
    print(f"  - {Agents.HISTORY}")
    print(f"  - {Agents.REGULATION}")
    print(f"  - {Agents.REPORTING}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()

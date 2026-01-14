# Gateway-Frontend Decoupling Implementation Plan

## Overview

This plan addresses three related improvements to the AGORA architecture:
1. Move ElevenLabs API key to backend with token exchange endpoint
2. Decouple the API gateway from HAI frontend so external developers can use the gateway independently
3. Add API key authentication prompt when `GATEWAY_REQUIRE_AUTH=true`

## Current State Analysis

### ElevenLabs Integration
- API key stored in `HAI/.env` as `VITE_ELEVENLABS_API_KEY`
- Key exposed client-side through Vite build system
- STT client (`HAI/src/lib/elevenlabs/sttClient.ts:62-77`) calls ElevenLabs API directly to get single-use tokens
- TTS client (`HAI/src/lib/elevenlabs/client.ts`) uses key directly for streaming

### Gateway-Frontend Coupling
- In production, Caddy proxies all traffic to HAI nginx (`Caddyfile:13`)
- HAI nginx routes `/ws`, `/api/*`, `/users`, `/sessions`, `/agents`, `/gateway`, `/health` to api-gateway (`HAI/nginx.gateway.conf:22-35`)
- Gateway cannot be accessed without HAI running

### Authentication Flow
- Gateway supports optional auth via `GATEWAY_REQUIRE_AUTH` and `GATEWAY_API_KEYS`
- WebSocket auth returns close code 4001 for unauthorized (`api-gateway/src/api_gateway/main.py:57-59`)
- HTTP auth returns 401 (`api-gateway/src/api_gateway/auth.py:28-43`)
- Frontend currently shows generic connection error, no auth prompt

### Key Discoveries:
- ElevenLabs STT already uses single-use tokens (`sttClient.ts:103`) - we just need to move the token fetch to backend
- TTS uses direct streaming with API key header (`client.ts:106`) - needs proxy endpoint
- Gateway close code 4001 can be detected in WebSocket client (`client.ts:215`)
- Caddy can route directly to gateway without HAI as intermediary

## Desired End State

After implementation:
1. ElevenLabs API key stored only on backend; frontend receives scoped tokens
2. Caddy routes directly to gateway for API paths; HAI is optional for gateway access
3. When auth is required, UI prompts for API key and stores it for session

### Verification:
- ElevenLabs voice features work without API key in frontend code
- Gateway accessible at `https://domain/api/*` and `/ws` without HAI running
- UI shows auth prompt when gateway returns 401/4001, allows key entry

## What We're NOT Doing

- Changing authentication mechanism (still using API keys)
- Adding rate limiting (noted but out of scope)
- Restricting CORS (acceptable for current stage)
- Server-side session storage for API keys (frontend localStorage is sufficient)
- Docker Compose profiles (keeping simple - Caddy restructure achieves the goal)

## Implementation Approach

Two phases:
1. **Phase 1**: ElevenLabs backend endpoints + API key authentication in frontend (merged)
2. **Phase 2**: Restructure Caddy to route directly to gateway

---

## Phase 1: ElevenLabs Backend & API Key Authentication

### Overview
Add ElevenLabs token proxy endpoints to api-gateway, create auth store and API key dialog in frontend, and update ElevenLabs clients to use backend + include auth headers.

### Changes Required:

#### 1. Gateway Configuration
**File**: `api-gateway/src/api_gateway/config.py`
**Changes**: Add ElevenLabs configuration fields

```python
# After line 36 (require_auth field)
elevenlabs_api_key: str = Field(
    default="",
    description="ElevenLabs API key for voice features (kept server-side)",
)
elevenlabs_voice_id: str = Field(
    default="pNInz6obpgDQGcFmaJgB",
    description="Default ElevenLabs voice ID",
)
```

#### 2. ElevenLabs Endpoints
**File**: `api-gateway/src/api_gateway/main.py`
**Changes**: Add ElevenLabs config, token, and TTS proxy endpoints

Add import at top:
```python
from fastapi.responses import StreamingResponse
```

Add endpoints after `/gateway/backends` (around line 48):

```python
@app.get("/gateway/elevenlabs/config")
async def get_elevenlabs_config(
    settings: Settings = Depends(get_settings),
    _auth: dict = Depends(verify_api_key_http),
):
    """Get ElevenLabs configuration (voice ID, whether voice is enabled)."""
    return {
        "enabled": bool(settings.elevenlabs_api_key),
        "voiceId": settings.elevenlabs_voice_id,
    }


@app.post("/gateway/elevenlabs/token")
async def get_elevenlabs_token(
    settings: Settings = Depends(get_settings),
    _auth: dict = Depends(verify_api_key_http),
):
    """Get a single-use token for ElevenLabs STT.

    The master API key stays server-side; client gets a scoped token.
    """
    if not settings.elevenlabs_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs not configured",
        )

    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe",
            headers={"xi-api-key": settings.elevenlabs_api_key},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"ElevenLabs token request failed: {response.text}",
            )

        return response.json()


@app.post("/gateway/elevenlabs/tts")
async def proxy_elevenlabs_tts(
    request: Request,
    settings: Settings = Depends(get_settings),
    _auth: dict = Depends(verify_api_key_http),
):
    """Proxy TTS requests to ElevenLabs, keeping API key server-side."""
    if not settings.elevenlabs_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs not configured",
        )

    import httpx

    body = await request.json()
    voice_id = body.pop("voice_id", settings.elevenlabs_voice_id)

    async def stream_tts():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        stream_tts(),
        media_type="audio/mpeg",
    )
```

#### 3. Update Docker Compose Files
**File**: `docker-compose.yml`
**Changes**: Add ElevenLabs env vars to api-gateway service (after `GATEWAY_REQUIRE_AUTH`)

```yaml
- GATEWAY_ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY:-}
- GATEWAY_ELEVENLABS_VOICE_ID=${ELEVENLABS_VOICE_ID:-pNInz6obpgDQGcFmaJgB}
```

**File**: `docker-compose.production.yml`
**Changes**: Same as above in api-gateway environment section

#### 4. Create Auth Store
**File**: `HAI/src/stores/useAuthStore.ts` (new file)

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthStore {
  apiKey: string | null;
  isAuthRequired: boolean | null; // null = unknown, true/false = determined
  authError: string | null;

  setApiKey: (key: string | null) => void;
  setAuthRequired: (required: boolean) => void;
  setAuthError: (error: string | null) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      apiKey: null,
      isAuthRequired: null,
      authError: null,

      setApiKey: (apiKey) => set({ apiKey, authError: null }),
      setAuthRequired: (isAuthRequired) => set({ isAuthRequired }),
      setAuthError: (authError) => set({ authError }),
      clearAuth: () => set({ apiKey: null, authError: null }),
    }),
    {
      name: 'agora-auth',
      partialize: (state) => ({ apiKey: state.apiKey }), // Only persist API key
    }
  )
);

// Helper for other modules to get the stored API key
export function getStoredApiKey(): string | null {
  return useAuthStore.getState().apiKey;
}
```

#### 5. Export Auth Store
**File**: `HAI/src/stores/index.ts`
**Changes**: Add auth store export

```typescript
export { useAuthStore, getStoredApiKey } from './useAuthStore';
```

#### 6. Create API Key Dialog Component
**File**: `HAI/src/components/auth/ApiKeyDialog.tsx` (new file)

```tsx
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { KeyRound, AlertCircle } from 'lucide-react';
import { useAuthStore } from '@/stores/useAuthStore';

interface ApiKeyDialogProps {
  open: boolean;
  onSubmit: (apiKey: string) => void;
}

export function ApiKeyDialog({ open, onSubmit }: ApiKeyDialogProps) {
  const [apiKey, setApiKey] = useState('');
  const authError = useAuthStore((state) => state.authError);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (apiKey.trim()) {
      onSubmit(apiKey.trim());
    }
  };

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-md" onPointerDownOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            API-sleutel vereist
          </DialogTitle>
          <DialogDescription>
            Deze applicatie vereist authenticatie. Voer uw API-sleutel in om door te gaan.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          {authError && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{authError}</AlertDescription>
            </Alert>
          )}

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="apiKey">API-sleutel</Label>
              <Input
                id="apiKey"
                type="password"
                placeholder="Voer uw API-sleutel in..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoFocus
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={!apiKey.trim()}>
              Verbinden
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

#### 7. Update HAI Environment
**File**: `HAI/src/lib/env.ts`
**Changes**: Remove ElevenLabs API key from schema, update helper functions

Remove from `envSchema`:
```typescript
// DELETE this line:
// VITE_ELEVENLABS_API_KEY: z.string().optional().default(''),
```

Update `getElevenLabsApiKey` function:
```typescript
export function getElevenLabsApiKey(): string {
  // Legacy function - API key now comes from backend
  console.warn('getElevenLabsApiKey() is deprecated. Use backend token endpoint.');
  return '';
}
```

#### 8. Update WebSocket Client
**File**: `HAI/src/lib/websocket/client.ts`
**Changes**: Detect auth errors and include API key in connection

Add import at top:
```typescript
import { getStoredApiKey } from '@/stores/useAuthStore';
```

Update `connect()` method (replace lines 69-77):
```typescript
connect(): void {
  if (this.isConnecting) {
    return;
  }

  if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
    return;
  }

  if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
    this.updateStatus('error');
    return;
  }

  this.isConnecting = true;
  this.isManualClose = false;
  const status = this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
  this.updateStatus(status);

  try {
    let url = this.config.url;

    // Append API key as query param if available
    const apiKey = getStoredApiKey();
    if (apiKey) {
      const urlObj = new URL(url, window.location.origin);
      urlObj.searchParams.set('token', apiKey);
      url = urlObj.toString();
    }

    this.ws = new WebSocket(url);
    this.setupEventHandlers();
  } catch (error) {
    this.isConnecting = false;
    this.handleError(new Error(`Failed to create WebSocket: ${error}`));
    this.scheduleReconnect();
  }
}
```

Update `onclose` handler in `setupEventHandlers()` (replace lines 215-223):
```typescript
this.ws.onclose = (event) => {
  this.isConnecting = false;

  // Detect auth failure (code 4001 from gateway)
  if (event.code === 4001) {
    this.updateStatus('error');
    this.handleError(new Error('AUTH_REQUIRED'));
    return; // Don't attempt reconnect for auth errors
  }

  if (!this.isManualClose) {
    this.scheduleReconnect();
  } else {
    this.updateStatus('disconnected');
  }
};
```

#### 9. Update useWebSocket Hook
**File**: `HAI/src/hooks/useWebSocket.ts`
**Changes**: Handle auth errors

Add import:
```typescript
import { useAuthStore } from '@/stores/useAuthStore';
```

Add near the top of the hook function:
```typescript
const setAuthRequired = useAuthStore((state) => state.setAuthRequired);
const setAuthError = useAuthStore((state) => state.setAuthError);
```

Update the error handling in `useEffect` where client errors are handled - wrap the existing error handler:
```typescript
// In the onError subscription callback, check for auth errors:
const unsubError = client.onError((error) => {
  if (error.message === 'AUTH_REQUIRED') {
    setAuthRequired(true);
    setAuthError('Authenticatie vereist. Voer uw API-sleutel in.');
  } else {
    setError(error);
  }
});
```

#### 10. Update App.tsx
**File**: `HAI/src/App.tsx`
**Changes**: Add ApiKeyDialog and auth flow

Add imports:
```typescript
import { ApiKeyDialog } from '@/components/auth/ApiKeyDialog';
import { useAuthStore } from '@/stores/useAuthStore';
```

Add in component body (after other store hooks):
```typescript
const isAuthRequired = useAuthStore((state) => state.isAuthRequired);
const setApiKey = useAuthStore((state) => state.setApiKey);
const setAuthRequired = useAuthStore((state) => state.setAuthRequired);

const handleApiKeySubmit = (apiKey: string) => {
  setApiKey(apiKey);
  setAuthRequired(false);
  reconnect(); // Retry connection with new key
};
```

Add in JSX, before `<MainLayout>`:
```tsx
{isAuthRequired === true && (
  <ApiKeyDialog
    open={true}
    onSubmit={handleApiKeySubmit}
  />
)}
```

#### 11. Update STT Client
**File**: `HAI/src/lib/elevenlabs/sttClient.ts`
**Changes**: Fetch token from backend

Update imports:
```typescript
import { getApiBaseUrl } from '@/lib/env';
import { getStoredApiKey } from '@/stores/useAuthStore';
```

Replace `fetchSingleUseToken` method (lines 62-77):
```typescript
private async fetchSingleUseToken(): Promise<string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  const apiKey = getStoredApiKey();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }

  const response = await fetch(`${getApiBaseUrl()}/gateway/elevenlabs/token`, {
    method: 'POST',
    headers,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch ElevenLabs token: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  return data.token;
}
```

Remove `getElevenLabsApiKey` import if present, and update `isConfigured()` method:
```typescript
isConfigured(): boolean {
  // Configuration is now handled by backend
  // We'll know if it's configured when we try to get a token
  return true;
}
```

#### 12. Update TTS Client
**File**: `HAI/src/lib/elevenlabs/client.ts`
**Changes**: Use backend proxy for TTS

Update imports:
```typescript
import { getApiBaseUrl, getElevenLabsVoiceId } from '@/lib/env';
import { getStoredApiKey } from '@/stores/useAuthStore';
```

In the `speak` method, replace the fetch call to ElevenLabs (around line 106) with:
```typescript
const headers: Record<string, string> = {
  'Content-Type': 'application/json',
};

const apiKey = getStoredApiKey();
if (apiKey) {
  headers['X-API-Key'] = apiKey;
}

const response = await fetch(`${getApiBaseUrl()}/gateway/elevenlabs/tts`, {
  method: 'POST',
  headers,
  body: JSON.stringify({
    text,
    voice_id: this.config.voiceId,
    model_id: 'eleven_multilingual_v2',
    voice_settings: {
      stability: 0.5,
      similarity_boost: 0.75,
    },
  }),
});
```

Update `isConfigured()` method similarly:
```typescript
isConfigured(): boolean {
  // Configuration is now handled by backend
  return true;
}
```

### Success Criteria:

#### Automated Verification:
- [ ] Gateway starts: `docker compose up api-gateway`
- [ ] Token endpoint responds: `curl -X POST http://localhost:8080/gateway/elevenlabs/token`
- [ ] Config endpoint responds: `curl http://localhost:8080/gateway/elevenlabs/config`
- [x] TypeScript compiles: `cd HAI && pnpm run type-check`
- [x] Lint passes: `cd HAI && pnpm run lint`
- [x] Build succeeds: `cd HAI && pnpm run build`

#### Manual Verification:
- [ ] With `GATEWAY_REQUIRE_AUTH=false`: App connects normally, no dialog shown
- [ ] With `GATEWAY_REQUIRE_AUTH=true` and no key: Dialog appears prompting for key
- [ ] With `GATEWAY_REQUIRE_AUTH=true` and wrong key: Dialog shows error, allows retry
- [ ] With `GATEWAY_REQUIRE_AUTH=true` and correct key: App connects, key persisted
- [ ] Page refresh with stored key: App reconnects automatically
- [ ] Voice mode (STT) works in the UI
- [ ] Text-to-speech playback works
- [ ] No ElevenLabs API key visible in browser dev tools (network tab, sources)

**Implementation Note**: After completing this phase, pause for manual confirmation that auth flow and voice features work correctly before proceeding to Phase 2.

---

## Phase 2: Gateway-Frontend Decoupling

### Overview
Restructure Caddy to route API traffic directly to gateway, making HAI optional. If HAI is not running, the gateway API still works - users just get a 502 for frontend routes.

### Changes Required:

#### 1. Update Caddyfile
**File**: `Caddyfile`
**Changes**: Add direct gateway routing before HAI fallback

```caddy
{$DOMAIN:localhost} {
	# Enable compression
	encode gzip

	# Health check endpoint for load balancers/monitoring
	handle /caddy-health {
		respond "OK" 200
	}

	# API Gateway routes - direct to gateway (HAI not required)
	@gateway {
		path /ws
		path /api/*
		path /users/*
		path /sessions/*
		path /agents/*
		path /gateway/*
		path /health
	}
	handle @gateway {
		reverse_proxy api-gateway:8000 {
			header_up X-Real-IP {remote_host}
			flush_interval -1
		}
	}

	# Frontend - reverse proxy to HAI nginx (optional)
	# If HAI is not running, users get 502 for frontend but API still works
	handle {
		reverse_proxy hai:80 {
			header_up X-Real-IP {remote_host}
			flush_interval -1
		}
	}

	# Security headers
	header {
		X-Frame-Options "SAMEORIGIN"
		X-Content-Type-Options "nosniff"
		X-XSS-Protection "1; mode=block"
		Referrer-Policy "strict-origin-when-cross-origin"
	}

	log {
		output stdout
		format json
		level INFO
	}
}
```

#### 2. Simplify HAI nginx config
**File**: `HAI/nginx.gateway.conf`
**Changes**: Remove gateway proxying (Caddy handles it now)

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # Runtime config injection
    location = /env-config.js {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
    }

    # SPA fallback - all routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml;
}
```

#### 3. Update docker-compose.production.yml dependencies
**File**: `docker-compose.production.yml`
**Changes**: Make HAI optional by updating Caddy's depends_on

In the `caddy` service, change `depends_on` to only require api-gateway:
```yaml
depends_on:
  api-gateway:
    condition: service_healthy
  # HAI is optional - frontend won't work without it but API will
```

### Success Criteria:

#### Automated Verification:
- [ ] Caddy starts with gateway only: Stop HAI, verify Caddy still runs
- [ ] Health endpoint works: `curl https://localhost/health`
- [ ] Gateway backends works: `curl https://localhost/gateway/backends`
- [ ] WebSocket connects or returns auth error: `curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" https://localhost/ws`

#### Manual Verification:
- [ ] Stop HAI container; verify API endpoints still respond
- [ ] Start HAI container; verify frontend loads and connects to gateway
- [ ] External developers can hit gateway API without running HAI

**Implementation Note**: After completing this phase, verify both gateway-only and full-stack modes work correctly.

---

## Testing Strategy

### Unit Tests:
- Auth store state management
- API key inclusion in WebSocket URL
- Token endpoint response handling

### Integration Tests:
- ElevenLabs token proxy flow
- Gateway auth with valid/invalid keys
- Frontend auth dialog flow

### Manual Testing Steps:
1. Start gateway with `GATEWAY_REQUIRE_AUTH=false`, verify normal operation
2. Enable auth (`GATEWAY_REQUIRE_AUTH=true`), verify dialog appears
3. Enter wrong key, verify error message
4. Enter correct key, verify connection succeeds
5. Refresh page, verify auto-reconnect with stored key
6. Test voice features (STT and TTS) with auth enabled
7. Stop HAI container, verify gateway API still responds

## Performance Considerations

- ElevenLabs token proxy adds one HTTP hop but tokens are cached for ~5 minutes
- TTS proxy streams directly, minimal latency impact
- API key stored in localStorage, no server round-trip for stored keys

## Migration Notes

1. Remove `VITE_ELEVENLABS_API_KEY` from HAI `.env` files after deployment
2. Add `GATEWAY_ELEVENLABS_API_KEY` to production environment
3. Existing sessions will need to re-enter API key if auth was not previously required

## References

- Current deployment: `thoughts/shared/research/2026-01-14-agora-deployment-gcloud-access.md`
- ElevenLabs STT API: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
- Caddy reverse_proxy: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy

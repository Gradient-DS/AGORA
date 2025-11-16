#!/usr/bin/env python3
"""
Diagnostic script to test OpenAI Realtime API connection.
Run this to verify your API key and connection work before starting the full server.
"""
import asyncio
import logging
import sys
import os
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

load_dotenv()

async def test_connection():
    """Test connection to OpenAI Realtime API."""
    api_key = os.getenv("APP_OPENAI_API_KEY")
    
    if not api_key:
        log.error("APP_OPENAI_API_KEY not found in environment")
        log.error("Please set it in your .env file")
        return False
    
    if not api_key.startswith("sk-"):
        log.error(f"API key doesn't look valid (should start with 'sk-'): {api_key[:10]}...")
        return False
    
    log.info("API key found, testing connection...")
    log.info(f"Using API key: {api_key[:10]}...")
    
    try:
        import websockets
        
        url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        
        log.info(f"Connecting to: {url}")
        
        async with websockets.connect(url, additional_headers=headers) as ws:
            log.info("✅ Connected successfully!")
            
            log.info("Sending session.update event...")
            import json
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": "You are a helpful assistant.",
                    "voice": "alloy",
                }
            }
            
            await ws.send(json.dumps(session_config))
            
            log.info("Waiting for response...")
            
            timeout = 5
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(message)
                log.info(f"✅ Received: {data.get('type')}")
                
                if data.get('type') == 'error':
                    log.error(f"❌ Error from OpenAI: {data.get('error')}")
                    return False
                
                log.info("✅ Connection test successful!")
                return True
                
            except asyncio.TimeoutError:
                log.warning(f"No response after {timeout}s, but connection was established")
                return True
                
    except websockets.exceptions.InvalidStatusCode as e:
        log.error(f"❌ Invalid status code: {e.status_code}")
        if e.status_code == 401:
            log.error("Authentication failed - check your API key")
        elif e.status_code == 403:
            log.error("Access denied - your API key may not have access to Realtime API")
        elif e.status_code == 404:
            log.error("Endpoint not found - check the model name")
        return False
        
    except Exception as e:
        log.error(f"❌ Connection failed: {e}", exc_info=True)
        return False

async def main():
    """Main entry point."""
    log.info("=" * 60)
    log.info("OpenAI Realtime API Connection Test")
    log.info("=" * 60)
    
    success = await test_connection()
    
    log.info("=" * 60)
    if success:
        log.info("✅ Test completed successfully!")
        log.info("You can now start the full server")
        sys.exit(0)
    else:
        log.error("❌ Test failed")
        log.error("Please fix the issues above before starting the server")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())


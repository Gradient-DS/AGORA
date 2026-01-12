#!/bin/sh
# Docker entrypoint for HAI frontend
# Injects runtime environment variables into the static build

# Generate runtime config from environment variables
cat > /usr/share/nginx/html/env-config.js << EOF
window.__RUNTIME_CONFIG__ = {
  ELEVENLABS_API_KEY: '${ELEVENLABS_API_KEY:-}',
  ELEVENLABS_VOICE_ID: '${ELEVENLABS_VOICE_ID:-pNInz6obpgDQGcFmaJgB}',
};
EOF

# Start nginx
exec nginx -g 'daemon off;'

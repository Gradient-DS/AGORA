from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


BLOCKED_PATTERNS = [
    r"ignore previous instructions",
    r"disregard.*instructions",
    r"system prompt",
    r"<script",
    r"javascript:",
]

SENSITIVE_OUTPUT_PATTERNS = [
    r"api[_-]?key",
    r"password",
    r"secret",
    r"token",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
]


class ModerationPipeline:
    """Input/output validation and moderation."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        if not enabled:
            log.warning("Moderation is DISABLED")

    async def validate_input(self, content: str) -> tuple[bool, str | None]:
        """Validate user input.

        Returns (is_valid, error_message).
        """
        if not self.enabled:
            return True, None

        # First check static patterns
        content_lower = content.lower()

        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, content_lower):
                log.warning("Blocked input pattern detected: %s", pattern)
                return False, "Input contains prohibited content"

        if len(content) > 10000:
            return False, "Input exceeds maximum length"

        if len(content.strip()) == 0:
            return False, "Input cannot be empty"

        # Future improvements:
        # 1. Integrate OpenAI Moderation API (consider latency)
        # 2. Use guardrails-ai for structured validation

        return True, None

    async def validate_output(self, content: str) -> tuple[bool, str | None]:
        """Validate assistant output.

        Returns (is_valid, error_message).
        """
        if not self.enabled:
            return True, None

        for pattern in SENSITIVE_OUTPUT_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                log.warning("Sensitive pattern detected in output: %s", pattern)
                return False, "Output contains sensitive information"

        return True, None

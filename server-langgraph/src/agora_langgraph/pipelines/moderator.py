"""Content moderation pipeline - matching server-openai behavior."""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


BLOCKED_PATTERNS = [
    r"\b(drop|delete|truncate)\s+table\b",
    r"\bexec\s*\(",
    r"<script>",
    r"javascript:",
]

MAX_INPUT_LENGTH = 10000
MAX_OUTPUT_LENGTH = 50000


class ModerationPipeline:
    """Content moderation for input and output validation."""

    def __init__(self, enabled: bool = True):
        """Initialize moderation pipeline.

        Args:
            enabled: Whether moderation is enabled
        """
        self.enabled = enabled
        if enabled:
            log.info("Moderation pipeline enabled")
        else:
            log.warning("Moderation pipeline DISABLED")

    async def validate_input(self, content: str) -> tuple[bool, str | None]:
        """Validate user input.

        Args:
            content: User message content

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.enabled:
            return True, None

        if len(content) > MAX_INPUT_LENGTH:
            return (
                False,
                f"Input exceeds maximum length of {MAX_INPUT_LENGTH} characters",
            )

        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                log.warning(f"Blocked pattern detected in input: {pattern}")
                return False, "Input contains potentially harmful content"

        return True, None

    async def validate_output(self, content: str) -> tuple[bool, str | None]:
        """Validate assistant output.

        Args:
            content: Assistant message content

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.enabled:
            return True, None

        if len(content) > MAX_OUTPUT_LENGTH:
            log.warning(f"Output exceeds maximum length: {len(content)} chars")
            return False, "Output exceeds maximum allowed length"

        return True, None

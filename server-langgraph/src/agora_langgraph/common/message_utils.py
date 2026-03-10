"""Utilities for extracting text from LangChain message content.

ChatOpenAI returns content as plain strings, but ChatGoogleGenerativeAI
returns structured lists like [{'type': 'text', 'text': '...', 'index': 0}].
This module normalizes both formats to plain strings.
"""

from __future__ import annotations

from typing import Any


def extract_text(content: Any) -> str:
    """Extract plain text from message content, regardless of provider format.

    Handles:
    - Plain strings (ChatOpenAI)
    - Lists of dicts with 'text' key (ChatGoogleGenerativeAI)
    - Lists of objects with .text attribute (Google Part objects)
    - Lists of plain strings

    Args:
        content: Message content — either a plain string or a list of
                 content parts (e.g. from ChatGoogleGenerativeAI).

    Returns:
        Extracted text as a plain string.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                # Accept dicts with type="text" or dicts with no type at all
                # (skip non-text types like "image_url")
                part_type = part.get("type")
                if part_type is None or part_type == "text":
                    text = part.get("text", "")
                    if text:
                        parts.append(text)
                elif part_type not in ("image_url", "binary"):
                    # Unrecognized type — try extracting "text" key as fallback
                    # (some providers use non-standard type values)
                    text = part.get("text", "")
                    if text:
                        parts.append(text)
            elif hasattr(part, "text"):
                # Handle Google Part objects or similar with .text attribute
                text = part.text
                if text:
                    parts.append(text)
        return "".join(parts)

    # Fallback: objects with .text attribute
    if hasattr(content, "text"):
        return content.text or ""

    return str(content)

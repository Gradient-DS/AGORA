"""Internal tools that don't require MCP servers."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from agents import FunctionTool
from agents.tool import ToolContext

if TYPE_CHECKING:
    from agora_openai.adapters.user_manager import UserManager

log = logging.getLogger(__name__)


# Module-level reference to UserManager (set during server startup)
_user_manager: "UserManager | None" = None


def set_user_manager(user_manager: "UserManager | None") -> None:
    """Set the UserManager instance for settings tools."""
    global _user_manager
    _user_manager = user_manager
    log.info(f"UserManager set for internal tools: {user_manager is not None}")


async def _update_user_settings_invoke(ctx: ToolContext[Any], args: str) -> str:
    """Invoke the update_user_settings tool.

    Args:
        ctx: Tool context (unused but required by SDK)
        args: JSON string with user_id and settings to update

    Returns:
        Confirmation message or error
    """
    if not _user_manager:
        return "Error: Instellingen service is niet beschikbaar."

    try:
        parsed_args = json.loads(args) if args else {}
    except json.JSONDecodeError:
        return "Error: Ongeldige parameters."

    user_id = parsed_args.get("user_id")
    spoken_text_type = parsed_args.get("spoken_text_type")
    interaction_mode = parsed_args.get("interaction_mode")

    if not user_id:
        return "Error: Geen gebruikers-ID opgegeven. Kan instellingen niet bijwerken."

    # Validate spoken_text_type
    valid_spoken_types = {"dictate", "summarize"}
    if spoken_text_type and spoken_text_type not in valid_spoken_types:
        return (
            f"Error: Ongeldige waarde '{spoken_text_type}' voor spraakweergave. "
            f"Geldige opties: 'dictate' (dicteren) of 'summarize' (samenvatten)."
        )

    # Validate interaction_mode
    valid_interaction_modes = {"feedback", "listen"}
    if interaction_mode and interaction_mode not in valid_interaction_modes:
        return (
            f"Error: Ongeldige waarde '{interaction_mode}' voor interactiemodus. "
            f"Geldige opties: 'feedback' (actief meedenken) of 'listen' (alleen noteren)."
        )

    # Build updates dict with only provided values
    updates: dict[str, Any] = {}
    if spoken_text_type:
        updates["spoken_text_type"] = spoken_text_type
    if interaction_mode:
        updates["interaction_mode"] = interaction_mode

    if not updates:
        return "Geen instellingen om bij te werken opgegeven."

    try:
        await _user_manager.update_preferences(user_id, updates)

        # Build confirmation message
        changes = []
        if spoken_text_type:
            mode_nl = "dicteren" if spoken_text_type == "dictate" else "samenvatten"
            changes.append(f"spraakweergave naar '{mode_nl}'")
        if interaction_mode:
            mode_nl = "feedback" if interaction_mode == "feedback" else "luisteren"
            changes.append(f"interactiemodus naar '{mode_nl}'"
                           + (" (zeg 'Agora' om me weer aan te spreken)" if interaction_mode == "listen" else ""))

        return f"Instellingen bijgewerkt: {', '.join(changes)}."

    except Exception as e:
        log.error(f"Failed to update user settings: {e}")
        return f"Error: Kon instellingen niet bijwerken: {e}"


def create_update_user_settings_tool() -> FunctionTool:
    """Create the update_user_settings FunctionTool for the OpenAI Agents SDK.

    Returns:
        FunctionTool for updating user settings
    """
    return FunctionTool(
        name="update_user_settings",
        description=(
            "Update user preferences/settings. Use this when the user wants to change "
            "their settings like speech mode (dictate vs summarize) or interaction mode "
            "(feedback vs listen). The user_id should be obtained from the conversation context."
        ),
        params_json_schema={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The ID of the user whose settings to update",
                },
                "spoken_text_type": {
                    "type": "string",
                    "enum": ["dictate", "summarize"],
                    "description": (
                        "Set to 'dictate' for full text reading or 'summarize' for "
                        "AI-generated TTS summaries"
                    ),
                },
                "interaction_mode": {
                    "type": "string",
                    "enum": ["feedback", "listen"],
                    "description": (
                        "Set to 'feedback' for active suggestions and engagement, or "
                        "'listen' for passive note-taking without interruptions"
                    ),
                },
            },
            "required": ["user_id"],
        },
        on_invoke_tool=_update_user_settings_invoke,
        strict_json_schema=False,
    )

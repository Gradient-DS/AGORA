import json
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from .prompts import EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ConversationExtractor:
    def __init__(self, openai_api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
    
    async def extract_from_conversation(
        self,
        messages: List[Dict[str, str]],
        existing_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        conversation_text = self._format_conversation(messages)
        
        logger.info(f"Extracting data from {len(messages)} messages")
        
        user_prompt = f"""Analyze the following inspection conversation and extract structured HAP report data.

CONVERSATION:
{conversation_text}

{"EXISTING EXTRACTED DATA (update/augment as needed):" if existing_data else ""}
{json.dumps(existing_data, indent=2, ensure_ascii=False) if existing_data else ""}

Extract all relevant information and return as JSON following the specified structure."""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                timeout=60.0,
            )
            
            extracted_data = json.loads(response.choices[0].message.content)
            
            logger.info(f"Extracted data with overall confidence: {extracted_data.get('overall_confidence', 0)}")
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error extracting conversation data: {e}", exc_info=True)
            return {
                "error": str(e),
                "overall_confidence": 0.0,
                "fields_needing_verification": []
            }
    
    def _format_conversation(self, messages: List[Dict[str, str]]) -> str:
        formatted_lines = []
        
        for msg in messages:
            role = msg.get("role", msg.get("type", "unknown"))
            content = msg.get("content", "")
            
            if role in ["user", "inspector"]:
                formatted_lines.append(f"INSPECTOR: {content}")
            elif role in ["assistant", "agent", "system"]:
                agent_id = msg.get("agent_id", "")
                prefix = f"AGORA ({agent_id})" if agent_id else "AGORA"
                formatted_lines.append(f"{prefix}: {content}")
        
        return "\n\n".join(formatted_lines)
    
    async def analyze_context(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        conversation_text = self._format_conversation(messages)
        
        analysis_prompt = f"""Analyze this inspection conversation and provide context:

CONVERSATION:
{conversation_text}

Return JSON with:
{{
  "business_type": "restaurant|retail|butcher|bakery|etc",
  "inspection_purpose": "routine|follow_up|complaint|food_poisoning",
  "key_topics_discussed": ["topic1", "topic2"],
  "severity_indicators": ["indicator1", "indicator2"],
  "inspector_concerns": ["concern1", "concern2"],
  "suggested_hygiene_code": "Hygiënecode type"
}}"""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing food safety inspection conversations."},
                    {"role": "user", "content": analysis_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                timeout=60.0,
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Error analyzing context: {e}")
            return {
                "business_type": "unknown",
                "inspection_purpose": "routine",
                "key_topics_discussed": [],
                "severity_indicators": [],
                "inspector_concerns": [],
                "suggested_hygiene_code": None
            }


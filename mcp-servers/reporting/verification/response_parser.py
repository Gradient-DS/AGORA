import json
import logging
from typing import Dict, Any, List
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class ResponseParser:
    def __init__(self, openai_api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
    
    async def parse_verification_responses(
        self,
        questions: List[Dict[str, Any]],
        responses: str | Dict[str, Any],
        existing_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        if isinstance(responses, str):
            responses_text = responses
        else:
            responses_text = json.dumps(responses, ensure_ascii=False)
        
        logger.info(f"Parsing verification responses for {len(questions)} questions")
        
        prompt = f"""Parse the inspector's verification responses and update the extracted inspection data.

QUESTIONS ASKED:
{json.dumps(questions, indent=2, ensure_ascii=False)}

INSPECTOR RESPONSES:
{responses_text}

EXISTING DATA TO UPDATE:
{json.dumps(existing_data, indent=2, ensure_ascii=False)}

Parse the responses and return updated JSON data that:
1. Incorporates the new information from responses
2. Updates the relevant fields identified in questions
3. Sets confidence to 1.0 for verified fields
4. Maintains all existing data that wasn't updated
5. Removes verified fields from fields_needing_verification

Return the complete updated data structure."""
        
        # Log prompt size for debugging
        prompt_size = len(prompt)
        logger.info(f"Response parser prompt size: {prompt_size} chars ({prompt_size / 1000:.1f}KB)")

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at parsing inspector responses and updating structured inspection data."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=60.0,
            )
            
            updated_data = json.loads(response.choices[0].message.content)
            
            logger.info("Successfully parsed verification responses")
            
            return updated_data
            
        except Exception as e:
            logger.error(f"Error parsing verification responses: {e}", exc_info=True)
            return existing_data
    
    def parse_simple_response(self, question: Dict[str, Any], response: str) -> Any:
        field = question.get("field", "")
        options = question.get("options", [])
        
        response_lower = response.lower().strip()
        
        if options:
            for option in options:
                if option.lower() in response_lower:
                    return option
        
        yes_words = ["ja", "yes", "correct", "klopt", "inderdaad"]
        no_words = ["nee", "no", "niet", "incorrect"]
        
        if any(word in response_lower for word in yes_words):
            return "Ja"
        elif any(word in response_lower for word in no_words):
            return "Nee"
        
        return response.strip()
    
    def merge_verification_data(
        self,
        original_data: Dict[str, Any],
        verification_answers: Dict[str, Any]
    ) -> Dict[str, Any]:
        merged = original_data.copy()
        
        for key, value in verification_answers.items():
            if "." in key:
                self._set_nested_value(merged, key, value)
            else:
                merged[key] = value
        
        if "fields_needing_verification" in merged:
            verified_fields = set(verification_answers.keys())
            merged["fields_needing_verification"] = [
                f for f in merged["fields_needing_verification"]
                if f not in verified_fields
            ]
        
        if "overall_confidence" in merged:
            total_fields = self._count_fields(merged)
            high_confidence_fields = self._count_high_confidence_fields(merged)
            merged["overall_confidence"] = high_confidence_fields / total_fields if total_fields > 0 else 0.0
        
        return merged
    
    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any) -> None:
        keys = path.split(".")
        current = data
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def _count_fields(self, data: Dict[str, Any], prefix: str = "") -> int:
        count = 0
        for key, value in data.items():
            if isinstance(value, dict) and key not in ["metadata", "conversation_history"]:
                count += self._count_fields(value, f"{prefix}{key}.")
            elif not isinstance(value, (list, dict)) and key not in ["error", "overall_confidence", "fields_needing_verification"]:
                count += 1
        return count
    
    def _count_high_confidence_fields(self, data: Dict[str, Any]) -> int:
        count = 0
        for key, value in data.items():
            if isinstance(value, dict) and key not in ["metadata", "conversation_history"]:
                count += self._count_high_confidence_fields(value)
            elif not isinstance(value, (list, dict)) and value is not None:
                count += 1
        return count


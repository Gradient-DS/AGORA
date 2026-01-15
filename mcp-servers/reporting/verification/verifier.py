import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from analyzers.prompts import VERIFICATION_PROMPT

logger = logging.getLogger(__name__)


class Verifier:
    def __init__(self, openai_api_key: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.confidence_threshold = 0.7
    
    async def generate_verification_questions(
        self,
        extracted_data: Dict[str, Any],
        max_questions: int = 3
    ) -> List[Dict[str, Any]]:
        fields_needing_verification = extracted_data.get("fields_needing_verification", [])
        
        missing_critical_fields = self._identify_missing_critical_fields(extracted_data)
        
        context = {
            "extracted_data": extracted_data,
            "fields_needing_verification": fields_needing_verification,
            "missing_critical_fields": missing_critical_fields,
            "max_questions": max_questions
        }
        
        logger.info(f"Generating verification questions for {len(fields_needing_verification)} uncertain fields and {len(missing_critical_fields)} missing fields")

        # Create a minimal version of extracted_data for the prompt (exclude verbose fields)
        minimal_data = self._create_minimal_data(extracted_data)

        prompt = f"""{VERIFICATION_PROMPT}

EXTRACTED DATA:
{json.dumps(minimal_data, indent=2, ensure_ascii=False)}

FIELDS NEEDING VERIFICATION (confidence < {self.confidence_threshold}):
{json.dumps(fields_needing_verification, indent=2, ensure_ascii=False)}

MISSING CRITICAL FIELDS:
{json.dumps(missing_critical_fields, indent=2, ensure_ascii=False)}

Generate up to {max_questions} verification questions prioritized by importance."""

        # Log prompt size for debugging
        prompt_size = len(prompt)
        logger.info(f"Verification prompt size: {prompt_size} chars ({prompt_size / 1000:.1f}KB)")
        if prompt_size > 50000:
            logger.warning(f"Large prompt detected ({prompt_size} chars), this may cause slow responses or errors")

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at identifying missing information in inspection reports and asking clarifying questions."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                timeout=60.0,
            )
            
            result = json.loads(response.choices[0].message.content)
            questions = result.get("questions", result.get("verification_questions", []))
            
            logger.info(f"Generated {len(questions)} verification questions")
            
            return questions[:max_questions]
            
        except Exception as e:
            logger.error(f"Error generating verification questions: {e}", exc_info=True)
            return self._generate_fallback_questions(missing_critical_fields)
    
    def _identify_missing_critical_fields(self, extracted_data: Dict[str, Any]) -> List[str]:
        missing = []
        
        critical_fields = [
            ("company_name", "Bedrijfsnaam"),
            ("company_address", "Bedrijfsadres"),
            ("inspector_name", "Naam inspecteur"),
            ("hygiene_general.compliant", "Hygiëne algemeen voldoet"),
            ("pest_control.pest_prevention_compliant", "Ongediertewering voldoet"),
            ("food_safety.storage_compliant", "Bewaren/opslag voldoet"),
        ]
        
        for field_path, field_label in critical_fields:
            if not self._get_nested_value(extracted_data, field_path):
                missing.append(field_label)
        
        if extracted_data.get("hygiene_general", {}).get("compliant") == "Nee":
            violations = extracted_data.get("hygiene_general", {}).get("violations", [])
            if not violations:
                missing.append("Specifieke hygiëneproblemen")
        
        if extracted_data.get("pest_control", {}).get("pest_present"):
            pest_types = extracted_data.get("pest_control", {}).get("pest_types", [])
            if not pest_types:
                missing.append("Type ongedierte")
        
        return missing
    
    def _create_minimal_data(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a minimal version of extracted_data for the verification prompt.

        Excludes verbose fields like full observations and long descriptions to keep
        the prompt size manageable.
        """
        # Fields to include at top level
        minimal = {
            "company_name": extracted_data.get("company_name"),
            "company_address": extracted_data.get("company_address"),
            "inspection_type": extracted_data.get("inspection_type"),
            "overall_confidence": extracted_data.get("overall_confidence"),
        }

        # For each section, include compliance status and violation count (not full details)
        for section in ["hygiene_general", "pest_control", "food_safety", "allergen_info"]:
            section_data = extracted_data.get(section, {})
            if isinstance(section_data, dict):
                minimal_section = {}
                for key, value in section_data.items():
                    if key == "violations":
                        # Just include count and types, not full descriptions
                        if isinstance(value, list):
                            minimal_section["violation_count"] = len(value)
                            minimal_section["violation_types"] = [v.get("type") for v in value if isinstance(v, dict)][:5]
                    elif key == "observations":
                        # Truncate long observations
                        if isinstance(value, str) and len(value) > 200:
                            minimal_section[key] = value[:200] + "..."
                        else:
                            minimal_section[key] = value
                    else:
                        minimal_section[key] = value
                minimal[section] = minimal_section

        # Include additional_info but truncate long strings
        additional = extracted_data.get("additional_info", {})
        if isinstance(additional, dict):
            minimal_additional = {}
            for key, value in additional.items():
                if isinstance(value, str) and len(value) > 200:
                    minimal_additional[key] = value[:200] + "..."
                else:
                    minimal_additional[key] = value
            minimal["additional_info"] = minimal_additional

        return minimal

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
    
    def _generate_fallback_questions(self, missing_fields: List[str]) -> List[Dict[str, Any]]:
        questions = []
        
        field_question_map = {
            "Bedrijfsnaam": {
                "question": "Wat is de naam van het geïnspecteerde bedrijf?",
                "field": "company_name",
                "importance": "critical",
                "options": None
            },
            "Bedrijfsadres": {
                "question": "Wat is het adres van het bedrijf?",
                "field": "company_address",
                "importance": "critical",
                "options": None
            },
            "Naam inspecteur": {
                "question": "Wat is uw naam?",
                "field": "inspector_name",
                "importance": "critical",
                "options": None
            },
            "Hygiëne algemeen voldoet": {
                "question": "Voldeed de algemene hygiëne aan de eisen?",
                "field": "hygiene_general.compliant",
                "importance": "critical",
                "options": ["Ja", "Nee", "Niet beoordeeld", "N.v.t."]
            },
            "Specifieke hygiëneproblemen": {
                "question": "Welke specifieke hygiëneproblemen zijn geconstateerd?",
                "field": "hygiene_general.violations",
                "importance": "high",
                "options": None
            },
            "Ongediertewering voldoet": {
                "question": "Voldeed de ongediertewering aan de eisen?",
                "field": "pest_control.pest_prevention_compliant",
                "importance": "high",
                "options": ["Ja", "Nee", "Niet beoordeeld", "N.v.t."]
            },
            "Type ongedierte": {
                "question": "Welk type ongedierte is waargenomen?",
                "field": "pest_control.pest_types",
                "importance": "high",
                "options": ["Muis", "Rat", "Vliegen", "Kakkerlakken", "Overige"]
            },
        }
        
        for missing in missing_fields[:3]:
            if missing in field_question_map:
                questions.append(field_question_map[missing])
        
        return questions
    
    def check_completeness(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        total_fields = 0
        filled_fields = 0
        missing_critical = []
        low_confidence_fields = []
        
        for section_name in ["hygiene_general", "pest_control", "food_safety", "allergen_info"]:
            section = extracted_data.get(section_name, {})
            if isinstance(section, dict):
                for field, value in section.items():
                    if field not in ["violations", "observations"]:
                        total_fields += 1
                        if value is not None:
                            filled_fields += 1
        
        missing_critical = self._identify_missing_critical_fields(extracted_data)
        
        fields_needing_verification = extracted_data.get("fields_needing_verification", [])
        
        completion_percentage = (filled_fields / total_fields * 100) if total_fields > 0 else 0
        
        return {
            "completion_percentage": completion_percentage,
            "total_fields": total_fields,
            "filled_fields": filled_fields,
            "missing_critical_fields": missing_critical,
            "low_confidence_fields": fields_needing_verification,
            "is_complete": completion_percentage >= 80 and len(missing_critical) == 0,
            "needs_verification": len(missing_critical) > 0 or len(fields_needing_verification) > 0
        }


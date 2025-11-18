import json
import logging
from typing import Dict, Any
from datetime import datetime
from models.hap_schema import HAPReport

logger = logging.getLogger(__name__)


class JSONGenerator:
    def generate(self, report: HAPReport) -> Dict[str, Any]:
        logger.info(f"Generating JSON report {report.metadata.report_id}")
        
        report_dict = report.model_dump(mode="json", exclude_none=False)
        
        report_dict["_generated_at"] = datetime.now().isoformat()
        report_dict["_version"] = "1.0"
        report_dict["_format"] = "HAP_JSON_v1"
        
        return report_dict
    
    def generate_summary(self, report: HAPReport) -> Dict[str, Any]:
        return {
            "report_id": report.metadata.report_id,
            "session_id": report.metadata.session_id,
            "company_name": report.metadata.company_name,
            "inspection_date": report.metadata.inspection_date.isoformat(),
            "inspection_type": report.metadata.inspection_type.value,
            "completion_percentage": report.metadata.completion_percentage,
            "overall_confidence": report.metadata.overall_confidence,
            "total_violations": len(report.all_violations),
            "serious_violations": len([v for v in report.all_violations if v.severity and "Ernstige" in v.severity.value]),
            "requires_follow_up": report.requires_follow_up,
            "enforcement_action_required": report.enforcement_action_required,
            "categories_assessed": {
                "hygiene_general": report.hygiene_general.compliant.value if report.hygiene_general.compliant else "Not assessed",
                "pest_control": report.pest_control.pest_prevention_compliant.value if report.pest_control.pest_prevention_compliant else "Not assessed",
                "food_safety": report.food_safety.storage_compliant.value if report.food_safety.storage_compliant else "Not assessed",
                "allergen_info": report.allergen_info.compliant.value if report.allergen_info.compliant else "Not assessed",
            },
        }
    
    def format_for_export(self, report: HAPReport) -> str:
        report_dict = self.generate(report)
        return json.dumps(report_dict, indent=2, ensure_ascii=False)


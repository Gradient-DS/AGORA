import logging
from typing import Dict, Any, Optional
from models.hap_schema import (
    HAPReport,
    InspectionMetadata,
    HygieneGeneral,
    PestControl,
    FoodSafetyInspection,
    AllergenInformation,
    AdditionalInformation,
    Violation,
)
from models.inspection_types import (
    ComplianceStatus,
    ViolationType,
    ViolationSeverity,
    InspectionType,
    HygieneCodeType,
    PestType,
    PestSeverity,
)

logger = logging.getLogger(__name__)


class FieldMapper:
    def __init__(self):
        self.compliance_mapping = {
            "ja": ComplianceStatus.YES,
            "yes": ComplianceStatus.YES,
            "nee": ComplianceStatus.NO,
            "no": ComplianceStatus.NO,
            "niet beoordeeld": ComplianceStatus.NOT_ASSESSED,
            "not assessed": ComplianceStatus.NOT_ASSESSED,
            "n.v.t.": ComplianceStatus.NOT_APPLICABLE,
            "n.v.t": ComplianceStatus.NOT_APPLICABLE,
            "nvt": ComplianceStatus.NOT_APPLICABLE,
            "not applicable": ComplianceStatus.NOT_APPLICABLE,
        }
    
    def map_to_hap_report(
        self,
        extracted_data: Dict[str, Any],
        session_id: str,
        report_id: str
    ) -> HAPReport:
        try:
            metadata = self._create_metadata(extracted_data, session_id, report_id)
            
            hygiene = self._map_hygiene_general(extracted_data.get("hygiene_general", {}))
            pest = self._map_pest_control(extracted_data.get("pest_control", {}))
            food_safety = self._map_food_safety(extracted_data.get("food_safety", {}))
            allergen = self._map_allergen_info(extracted_data.get("allergen_info", {}))
            additional = self._map_additional_info(extracted_data.get("additional_info", {}))
            
            report = HAPReport(
                metadata=metadata,
                hygiene_general=hygiene,
                pest_control=pest,
                food_safety=food_safety,
                allergen_info=allergen,
                additional_info=additional,
                conversation_history=extracted_data.get("conversation_history", []),
            )
            
            report.aggregate_violations()
            
            completion = report.calculate_completion()
            report.metadata.completion_percentage = completion
            report.metadata.overall_confidence = extracted_data.get("overall_confidence", 0.0)
            
            logger.info(f"Mapped report with {len(report.all_violations)} violations, {completion:.1f}% complete")
            
            return report
            
        except Exception as e:
            logger.error(f"Error mapping to HAP report: {e}", exc_info=True)
            raise
    
    def _create_metadata(self, data: Dict[str, Any], session_id: str, report_id: str) -> InspectionMetadata:
        inspection_type_str = data.get("inspection_type", "Reguliere inspectie")
        inspection_type = InspectionType.REGULAR
        
        type_mapping = {
            "reguliere": InspectionType.REGULAR,
            "herinspectie": InspectionType.FOLLOW_UP,
            "klacht": InspectionType.COMPLAINT,
            "spoed": InspectionType.EMERGENCY,
            "voedselvergiftiging": InspectionType.FOOD_POISONING,
        }
        
        for key, value in type_mapping.items():
            if key in inspection_type_str.lower():
                inspection_type = value
                break
        
        return InspectionMetadata(
            report_id=report_id,
            session_id=session_id,
            company_name=data.get("company_name"),
            company_address=data.get("company_address"),
            company_id=data.get("company_id"),
            inspection_type=inspection_type,
            inspector_name=data.get("inspector_name"),
        )
    
    def _map_hygiene_general(self, data: Dict[str, Any]) -> HygieneGeneral:
        violations = []
        for v in data.get("violations", []):
            violations.append(self._map_violation(v))
        
        return HygieneGeneral(
            compliant=self._map_compliance(data.get("compliant")),
            violations=violations,
            observations=data.get("observations"),
            washing_facilities=self._map_compliance(data.get("washing_facilities")),
            ventilation=self._map_compliance(data.get("ventilation")),
            sanitary_facilities=self._map_compliance(data.get("sanitary_facilities")),
            lighting=self._map_compliance(data.get("lighting")),
            drainage=self._map_compliance(data.get("drainage")),
            toilets=self._map_compliance(data.get("toilets")),
            floor_condition=self._map_compliance(data.get("floor_condition")),
            ceiling_condition=self._map_compliance(data.get("ceiling_condition")),
            wall_condition=self._map_compliance(data.get("wall_condition")),
            equipment_cleanliness=self._map_compliance(data.get("equipment_cleanliness")),
            equipment_maintenance=self._map_compliance(data.get("equipment_maintenance")),
        )
    
    def _map_pest_control(self, data: Dict[str, Any]) -> PestControl:
        violations = []
        for v in data.get("violations", []):
            violations.append(self._map_violation(v))
        
        pest_types = []
        for pt in data.get("pest_types", []):
            try:
                pest_types.append(PestType(pt))
            except ValueError:
                logger.warning(f"Unknown pest type: {pt}")
        
        pest_severity = None
        severity_str = data.get("pest_severity")
        if severity_str:
            try:
                pest_severity = PestSeverity(severity_str)
            except ValueError:
                logger.warning(f"Unknown pest severity: {severity_str}")
        
        return PestControl(
            pest_prevention_compliant=self._map_compliance(data.get("pest_prevention_compliant")),
            pest_control_compliant=self._map_compliance(data.get("pest_control_compliant")),
            violations=violations,
            pest_present=data.get("pest_present", False),
            pest_types=pest_types,
            pest_severity=pest_severity,
            pest_other_description=data.get("pest_other_description"),
            observations=data.get("observations"),
        )
    
    def _map_food_safety(self, data: Dict[str, Any]) -> FoodSafetyInspection:
        violations = []
        for v in data.get("violations", []):
            violations.append(self._map_violation(v))
        
        return FoodSafetyInspection(
            storage_compliant=self._map_compliance(data.get("storage_compliant")),
            preparation_cooling_compliant=self._map_compliance(data.get("preparation_cooling_compliant")),
            presentation_compliant=self._map_compliance(data.get("presentation_compliant")),
            violations=violations,
            temperature_violations=data.get("temperature_violations", []),
            unsafe_products=data.get("unsafe_products", []),
            observations=data.get("observations"),
        )
    
    def _map_allergen_info(self, data: Dict[str, Any]) -> AllergenInformation:
        violations = []
        for v in data.get("violations", []):
            violations.append(self._map_violation(v))
        
        return AllergenInformation(
            compliant=self._map_compliance(data.get("compliant")),
            information_method=data.get("information_method"),
            violations=violations,
            written_info_available=self._map_compliance(data.get("written_info_available")),
            oral_info_adequate=self._map_compliance(data.get("oral_info_adequate")),
            signage_present=self._map_compliance(data.get("signage_present")),
            observations=data.get("observations"),
        )
    
    def _map_additional_info(self, data: Dict[str, Any]) -> AdditionalInformation:
        hygiene_code = None
        code_str = data.get("hygiene_code_used")
        if code_str:
            for code in HygieneCodeType:
                if code_str.lower() in code.value.lower():
                    hygiene_code = code
                    break
        
        return AdditionalInformation(
            inspection_location_description=data.get("inspection_location_description"),
            hygiene_code_used=hygiene_code,
            mobile_temporary_location=data.get("mobile_temporary_location", False),
            location_type=data.get("location_type"),
            outdoor_temperature=data.get("outdoor_temperature"),
            repeat_violation=data.get("repeat_violation", False),
            repeat_violation_details=data.get("repeat_violation_details"),
            action_required=data.get("action_required"),
            inspector_notes=data.get("inspector_notes"),
        )
    
    def _map_violation(self, data: Dict[str, Any]) -> Violation:
        violation_type = ViolationType.OTHER
        type_str = data.get("type", "")
        
        for vt in ViolationType:
            if type_str.lower() in vt.value.lower() or vt.value.lower() in type_str.lower():
                violation_type = vt
                break
        
        severity = None
        severity_str = data.get("severity")
        if severity_str:
            for vs in ViolationSeverity:
                if severity_str.lower() in vs.value.lower():
                    severity = vs
                    break
        
        return Violation(
            type=violation_type,
            severity=severity,
            description=data.get("description", ""),
            location=data.get("location"),
            evidence=data.get("evidence"),
            control_element_id=data.get("control_element_id"),
            confidence=data.get("confidence", 0.8),
        )
    
    def _map_compliance(self, value: Any) -> Optional[ComplianceStatus]:
        if value is None:
            return None
        
        value_str = str(value).lower().strip()
        return self.compliance_mapping.get(value_str)


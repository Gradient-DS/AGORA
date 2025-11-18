from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .inspection_types import (
    ViolationSeverity,
    ComplianceStatus,
    InspectionType,
    ViolationType,
    HygieneCodeType,
    PestType,
    PestSeverity,
)


class FieldValue(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source: Optional[str] = None
    needs_verification: bool = False


class Violation(BaseModel):
    type: ViolationType
    severity: Optional[ViolationSeverity] = None
    description: str
    location: Optional[str] = None
    evidence: Optional[str] = None
    control_element_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class HygieneGeneral(BaseModel):
    compliant: Optional[ComplianceStatus] = None
    violations: List[Violation] = Field(default_factory=list)
    observations: Optional[str] = None
    washing_facilities: Optional[ComplianceStatus] = None
    ventilation: Optional[ComplianceStatus] = None
    sanitary_facilities: Optional[ComplianceStatus] = None
    lighting: Optional[ComplianceStatus] = None
    drainage: Optional[ComplianceStatus] = None
    toilets: Optional[ComplianceStatus] = None
    floor_condition: Optional[ComplianceStatus] = None
    ceiling_condition: Optional[ComplianceStatus] = None
    wall_condition: Optional[ComplianceStatus] = None
    equipment_cleanliness: Optional[ComplianceStatus] = None
    equipment_maintenance: Optional[ComplianceStatus] = None


class PestControl(BaseModel):
    pest_prevention_compliant: Optional[ComplianceStatus] = None
    pest_control_compliant: Optional[ComplianceStatus] = None
    violations: List[Violation] = Field(default_factory=list)
    pest_present: bool = False
    pest_types: List[PestType] = Field(default_factory=list)
    pest_severity: Optional[PestSeverity] = None
    pest_other_description: Optional[str] = None
    observations: Optional[str] = None


class FoodSafetyInspection(BaseModel):
    storage_compliant: Optional[ComplianceStatus] = None
    preparation_cooling_compliant: Optional[ComplianceStatus] = None
    presentation_compliant: Optional[ComplianceStatus] = None
    violations: List[Violation] = Field(default_factory=list)
    temperature_violations: List[Dict[str, Any]] = Field(default_factory=list)
    unsafe_products: List[str] = Field(default_factory=list)
    observations: Optional[str] = None


class AllergenInformation(BaseModel):
    compliant: Optional[ComplianceStatus] = None
    information_method: Optional[str] = None
    violations: List[Violation] = Field(default_factory=list)
    written_info_available: Optional[ComplianceStatus] = None
    oral_info_adequate: Optional[ComplianceStatus] = None
    signage_present: Optional[ComplianceStatus] = None
    observations: Optional[str] = None


class AdditionalInformation(BaseModel):
    inspection_location_description: Optional[str] = None
    hygiene_code_used: Optional[HygieneCodeType] = None
    hygiene_code_assessed_against: Optional[HygieneCodeType] = None
    mobile_temporary_location: bool = False
    location_type: Optional[str] = None
    outdoor_temperature: Optional[float] = None
    repeat_violation: bool = False
    repeat_violation_details: Optional[str] = None
    action_required: Optional[str] = None
    inspector_notes: Optional[str] = None
    rvb_additional_info: Optional[ComplianceStatus] = None


class InspectionMetadata(BaseModel):
    report_id: str
    session_id: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    inspection_date: datetime = Field(default_factory=datetime.now)
    inspection_type: InspectionType = InspectionType.REGULAR
    inspector_name: Optional[str] = None
    inspector_id: Optional[str] = None
    product_name: str = "Reguliere inspectie HAP"
    product_version: str = "6.02"
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    completion_percentage: float = Field(ge=0.0, le=100.0, default=0.0)


class HAPReport(BaseModel):
    metadata: InspectionMetadata
    hygiene_general: HygieneGeneral = Field(default_factory=HygieneGeneral)
    pest_control: PestControl = Field(default_factory=PestControl)
    food_safety: FoodSafetyInspection = Field(default_factory=FoodSafetyInspection)
    allergen_info: AllergenInformation = Field(default_factory=AllergenInformation)
    additional_info: AdditionalInformation = Field(default_factory=AdditionalInformation)
    
    all_violations: List[Violation] = Field(default_factory=list)
    requires_follow_up: bool = False
    enforcement_action_required: bool = False
    
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    verification_questions: List[str] = Field(default_factory=list)
    
    def calculate_completion(self) -> float:
        total_fields = 0
        filled_fields = 0
        
        for section in [self.hygiene_general, self.pest_control, self.food_safety, self.allergen_info]:
            for field_name, field_value in section.model_dump().items():
                if field_name not in ["violations", "observations", "temperature_violations", "unsafe_products", "pest_types"]:
                    total_fields += 1
                    if field_value is not None and field_value != [] and field_value != False:
                        filled_fields += 1
        
        return (filled_fields / total_fields * 100) if total_fields > 0 else 0.0
    
    def aggregate_violations(self) -> None:
        self.all_violations = []
        self.all_violations.extend(self.hygiene_general.violations)
        self.all_violations.extend(self.pest_control.violations)
        self.all_violations.extend(self.food_safety.violations)
        self.all_violations.extend(self.allergen_info.violations)
        
        serious_violations = [v for v in self.all_violations if v.severity == ViolationSeverity.SERIOUS]
        self.requires_follow_up = len(self.all_violations) > 0
        self.enforcement_action_required = len(serious_violations) > 0


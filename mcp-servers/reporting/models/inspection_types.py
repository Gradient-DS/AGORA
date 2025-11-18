from enum import Enum


class ViolationSeverity(str, Enum):
    SERIOUS = "Ernstige overtreding"
    MODERATE = "Overtreding"
    MINOR = "Geringe overtreding"
    NONE = "Geen overtreding"


class ComplianceStatus(str, Enum):
    YES = "Ja"
    NO = "Nee"
    NOT_ASSESSED = "Niet beoordeeld"
    NOT_APPLICABLE = "N.v.t."


class InspectionType(str, Enum):
    REGULAR = "Reguliere inspectie"
    FOLLOW_UP = "Herinspectie"
    COMPLAINT = "Klachtinspectie"
    EMERGENCY = "Spoedcontrole"
    FOOD_POISONING = "Voedselvergiftiging"


class ViolationType(str, Enum):
    HYGIENE_NOT_CLEAN = "bedrijfsruimte(s) niet schoon"
    HYGIENE_NOT_MAINTAINED = "bedrijfsruimte(s) niet goed onderhouden"
    HYGIENE_STRUCTURAL = "bedrijfsruimte(s) bouwkundig onvoldoende"
    EQUIPMENT_NOT_CLEAN = "apparatuur niet schoon"
    EQUIPMENT_MAINTENANCE = "apparatuur onderhoud/constructie"
    
    FOOD_CONTAMINATION = "besmetting van levensmiddelen"
    TEMP_COOLED_UNPACKED = "(productbeoordeling) temperatuur gekoeld onverpakt"
    TEMP_COOLED_PACKED = "(productbeoordeling) temperatuur gekoeld voorverpakt"
    TEMP_WARM = "(productbeoordeling) temperatuur warm"
    UNSAFE_PRODUCT_UNSUITABLE = "(productbeoordeling) onveilig product (ongeschikt)"
    UNSAFE_PRODUCT_HARMFUL = "(productbeoordeling) onveilig product (schadelijk)"
    EXPIRY_DATE = "(productbeoordeling) houdbaarheid uiterste consumptiedatum (TGT)"
    
    PEST_CONTROL = "Ongediertebestrijding"
    PEST_PREVENTION_CONSTRUCTION = "Constructie, etc. (ongediertewering)"
    PEST_WINDOWS_NO_SCREEN = "Ramen / andere openingen zonder hor"
    PETS_IN_PREMISES = "Huisdieren in bedrijfsruimten"
    
    ALLERGEN_INFO_MISSING = "Er wordt geen allergeneninformatie aangeboden"
    ALLERGEN_INFO_UNCLEAR = "allergeneninformatie niet duidelijk"
    
    NO_HYGIENE_CODE = "geen (dekkende) hygiënecode geen vvp"
    LABELING = "Etikettering onvoldoende"
    DOCUMENTATION_MISSING = "Documentatie ontbreekt"
    CE_MARKING_MISSING = "Geen CE-markering"
    
    OTHER = "overig"


class HygieneCodeType(str, Enum):
    HORECA = "Hygiënecode voor de Horeca"
    CBL = "CBL hygiënecode"
    AGF = "Hygiënecode voor de AGF-detailhandel"
    CATERING = "Hygiënecode voor Contract- en inflightcatering"
    SVO = "Hygiënecode SVO"
    FISH = "Hygiënecode voor de visdetailhandel"
    ICE_CREAM = "Hygiënecode voor de ambachtelijke consumptie-ijsbereider"
    BUTCHER = "Hygiënecode voor het Slagers- en Poeliersbedrijf"
    BAKERY = "Hygiënecode voor de Brood en banketbakkersij"
    CARE = "Hygiënecode voor zorginstellingen, woonvormen en Defensie"
    OTHER = "Overig"
    NONE = "Geen"


class PestType(str, Enum):
    MOUSE = "Muis"
    RAT = "Rat"
    FLIES = "Vliegen"
    COCKROACHES = "Kakkerlakken"
    OTHER = "Overige"


class PestSeverity(str, Enum):
    MINIMAL = "Minimale overlast"
    MODERATE = "Matige overlast"
    SEVERE = "Veel overlast"
    ABSENT = "Afwezig"


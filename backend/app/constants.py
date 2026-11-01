"""Canonical value lists shared by validation, matching and the catalogue."""
STATES_UT = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka",
    "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]
STATE_ALIASES = {
    "nct of delhi": "Delhi", "delhi (nct)": "Delhi", "new delhi": "Delhi",
    "pondicherry": "Puducherry", "orissa": "Odisha",
    "andaman & nicobar islands": "Andaman and Nicobar Islands",
    "jammu & kashmir": "Jammu and Kashmir",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
}
BUSINESS_TYPES = [
    "retail_trade", "manufacturing", "services", "food_processing", "artisan_craft",
    "technology", "agriculture_allied", "street_vending", "other",
]
OWNERSHIP = [
    "individual_proprietorship", "partnership", "llp", "private_limited_company",
    "cooperative", "self_help_group", "other_unsure",
]
STAGES = ["idea_pre_launch", "newly_operating", "established", "expanding"]
ASSISTANCE_NEEDS = [
    "credit_loan", "subsidy_grant", "equipment_technology", "training_mentoring",
    "market_access", "working_capital", "low_income_assistance", "other",
]
REGISTRATION = ["registered", "not_registered", "in_progress", "unsure"]
JURISDICTIONS = ["central", "state_ut", "local"]
SCHEME_STATUSES = ["active", "possibly_changed", "expired", "withdrawn", "unverified"]
INACTIVE_STATUSES = {"expired", "withdrawn", "unverified"}
REQUIREMENT_TYPES = ["required", "conditional", "confirm"]
REQUIREMENT_LABELS = {
    "required": "Required",
    "conditional": "Conditional",
    "confirm": "Confirm with official source",
}
OPERATORS = ["eq", "ne", "in", "not_in", "lte", "gte", "between", "contains_any"]
RULE_FIELDS = [
    "state_ut", "district", "business_type", "ownership_category", "annual_turnover_inr",
    "employee_count", "business_stage", "assistance_need", "registration_status",
]
CATALOGUE_NOTICE = (
    "Scheme information is loaded from the BenefitBridge database and may be incomplete or out of date. "
    "Check the last-verified date and confirm details on the official source before acting."
)

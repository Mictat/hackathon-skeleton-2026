from app.agents import composite_confidence
from app.agents.classification import regex_classify


def test_regex_obvious_hits():
    assert regex_classify("email_addr") == "email"
    assert regex_classify("eml_addr") == "email"  # email beats address (priority)
    assert regex_classify("mob_no") == "phone"
    assert regex_classify("date_of_birth") == "date_of_birth"
    assert regex_classify("home_addr_txt") == "address"
    assert regex_classify("monthly_income") == "income"


def test_regex_leaves_hard_cases_to_llm():
    assert regex_classify("vendor_iban") is None  # entity, not person — LLM's call
    assert regex_classify("merchant_desc") is None
    assert regex_classify("nm") is None  # cryptic — LLM's home turf
    assert regex_classify("fld_02") is None


def test_composite_confidence():
    full = composite_confidence({"classification": 0.95, "ownership": 0.90, "description": 0.85})
    assert abs(full - 0.91) < 0.001
    missing_desc = composite_confidence({"classification": 0.95, "ownership": 0.90})
    assert abs(missing_desc - 0.7975) < 0.001

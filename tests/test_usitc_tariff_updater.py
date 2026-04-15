from decimal import Decimal

from scripts.update_tariffs_from_usitc import _choose_best_usitc_row, parse_general_rate


def test_parse_general_rate_free():
    rate, rate_type, status = parse_general_rate("Free")
    assert rate == Decimal("0.00")
    assert rate_type == "duty_free"
    assert status == "ok_free"


def test_parse_general_rate_ad_valorem_percent():
    rate, rate_type, status = parse_general_rate("4.0%")
    assert rate == Decimal("4.00")
    assert rate_type == "ad_valorem"
    assert status == "ok_ad_valorem"


def test_parse_general_rate_mixed_expression():
    rate, rate_type, status = parse_general_rate("5.0% + 1.4¢/kg")
    assert rate == Decimal("5.00")
    assert rate_type == "mixed"
    assert status == "ok_mixed"


def test_parse_general_rate_specific_only():
    rate, rate_type, status = parse_general_rate("0.43¢/kg")
    assert rate is None
    assert rate_type == "specific"
    assert status == "non_ad_valorem"


def test_choose_best_usitc_row_prefers_exact_hts():
    rows = [
        {"htsno": "0703.20.00.05", "general": ""},
        {"htsno": "0703.20.00", "general": "0.43¢/kg"},
        {"htsno": "0703.20.00.10", "general": ""},
    ]
    selected = _choose_best_usitc_row(rows, target_hts="0703.20.00")
    assert selected is not None
    assert selected["htsno"] == "0703.20.00"

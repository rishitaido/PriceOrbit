from decimal import Decimal

from app.services.tariff_resolver_service import TariffResolverService


CSV_CONTENT = """product_name,hts_code,tariff_rate,origin_country,import_dependency
Apples,0808.10.00,0.00,United States,Low
Beef Steak,0201.30.02,4.00,United States,Low
"""


def _make_resolver(tmp_path):
    csv_path = tmp_path / "tariffs.csv"
    csv_path.write_text(CSV_CONTENT, encoding="utf-8")
    return TariffResolverService(csv_path=str(csv_path), confidence_threshold=80)


def test_resolve_by_exact_name(tmp_path):
    resolver = _make_resolver(tmp_path)

    result = resolver.resolve(product_name="Apples")

    assert result.matched is True
    assert result.match_strategy == "name_exact"
    assert result.tariff_rate == Decimal("0.00")
    assert result.rate_type == "duty_free"
    assert result.review_status == "verified"


def test_resolve_by_exact_hts_and_origin(tmp_path):
    resolver = _make_resolver(tmp_path)

    result = resolver.resolve(
        product_name="Unknown Label",
        hts_code="0201.30.02",
        origin_country="United States",
    )

    assert result.matched is True
    assert result.match_strategy == "hts_origin_exact"
    assert result.tariff_rate == Decimal("4.00")
    assert result.rate_type == "ad_valorem"
    assert result.confidence_score == Decimal("100.00")


def test_resolve_by_token_similarity_marks_needs_review_when_below_threshold(tmp_path):
    resolver = _make_resolver(tmp_path)

    result = resolver.resolve(product_name="Fresh Apples")

    assert result.matched is True
    assert result.match_strategy == "token_similarity"
    assert result.review_status == "needs_review"
    assert Decimal("60") <= result.confidence_score < Decimal("80")


def test_resolve_unmatched(tmp_path):
    resolver = _make_resolver(tmp_path)

    result = resolver.resolve(product_name="Industrial Solvent")

    assert result.matched is False
    assert result.match_strategy == "unmatched"
    assert result.review_status == "incomplete"
    assert result.tariff_rate is None

from datetime import date
from decimal import Decimal

import pdfplumber
import pytest
from helpers import SAMPLES

from lossrun.models import Claim, LineOfCoverage
from lossrun.parsers import harborline, keystone, northfield, pinecrest
from lossrun.parsers.base import ParseError, RunBuilder, money, parse_date
from lossrun.parsers.registry import detect_parser


def parse_sample(parser, name):
    with pdfplumber.open(SAMPLES / name) as pdf:
        return parser.parse(pdf, name)


def make_builder() -> RunBuilder:
    builder = RunBuilder(
        source_file="a.pdf",
        parser_name="test",
        carrier="Carrier",
        insured_name="Insured",
        line=LineOfCoverage.GL,
        valuation_date=date(2026, 9, 1),
        page_count=1,
    )
    builder.term("P-1", date(2025, 1, 1), date(2026, 1, 1), page=1)
    return builder


def add_claim(builder: RunBuilder, **overrides) -> None:
    fields = dict(
        policy_number="P-1",
        claim_number="C-1",
        date_of_loss=date(2025, 3, 1),
        status="Open",
        paid="$1,000.00",
        reserved="500.00",
        incurred="1,500.00",
        page=1,
    )
    builder.claim(**(fields | overrides))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12,400.00", "12400.00"),
        ("$8,920.50", "8920.50"),
        ("0.00", "0.00"),
        ("(150.00)", "-150.00"),
    ],
)
def test_money(text, expected):
    assert money(text) == Decimal(expected)


def test_money_rejects_text_that_is_not_an_amount():
    with pytest.raises(ParseError):
        money("n/a")


def test_parse_date():
    assert parse_date(" 14-Aug-2021 ", "%d-%b-%Y") == date(2021, 8, 14)


def test_parse_date_rejects_wrong_format():
    with pytest.raises(ParseError):
        parse_date("2021-08-14", "%m/%d/%Y")


@pytest.mark.parametrize(
    ("header", "parser"),
    [
        ("NORTHFIELD MUTUAL INSURANCE COMPANY", northfield),
        ("Harborline Casualty Group", harborline),
        ("PINECREST SPECIALTY UNDERWRITERS", pinecrest),
        ("Keystone Claims Administrators", keystone),
    ],
)
def test_detect_parser(header, parser):
    assert detect_parser(header + "\nLoss Run") is parser


def test_detect_parser_returns_none_for_unknown_carrier():
    assert detect_parser("ACME INDEMNITY\nLoss Run") is None


def test_detect_parser_ignores_carriers_named_further_down_the_page():
    text = "Keystone Claims Administrators\n\n\n\n\non behalf of Northfield Mutual"
    assert detect_parser(text) is keystone


def test_builder_claim_reads_status_and_amounts():
    builder = make_builder()
    add_claim(builder)
    [claim] = builder.claims
    assert (claim.status, claim.paid, claim.reserved, claim.incurred) == (
        "open",
        Decimal("1000.00"),
        Decimal("500.00"),
        Decimal("1500.00"),
    )


def test_builder_claim_takes_policy_period_from_its_term():
    builder = make_builder()
    add_claim(builder)
    [claim] = builder.claims
    assert (claim.policy_period_start, claim.policy_period_end) == (
        date(2025, 1, 1),
        date(2026, 1, 1),
    )


def test_builder_rejects_claim_on_unknown_policy():
    with pytest.raises(ParseError, match="unknown policy"):
        add_claim(make_builder(), policy_number="P-2")


def test_builder_rejects_policy_with_two_different_periods():
    with pytest.raises(ParseError, match="two different periods"):
        make_builder().term("P-1", date(2024, 1, 1), date(2025, 1, 1), page=1)


def test_builder_check_totals_accepts_matching_totals():
    builder = make_builder()
    add_claim(builder)
    builder.check_totals(
        "total", builder.claims, count=1, paid="1,000.00", reserved="500.00", incurred="1,500.00"
    )


def test_builder_check_totals_rejects_wrong_amount():
    builder = make_builder()
    add_claim(builder)
    with pytest.raises(ParseError, match="total paid"):
        builder.check_totals(
            "total", builder.claims, count=1, paid="999.00", reserved="500.00", incurred="1,500.00"
        )


def test_builder_check_totals_rejects_wrong_count():
    builder = make_builder()
    add_claim(builder)
    with pytest.raises(ParseError, match="claim count"):
        builder.check_totals(
            "total",
            builder.claims,
            count=2,
            paid="1,000.00",
            reserved="500.00",
            incurred="1,500.00",
        )


def test_builder_build_requires_a_policy_term():
    builder = make_builder()
    builder.terms.clear()
    with pytest.raises(ParseError, match="no policy terms"):
        builder.build()


def test_northfield_parses_a_claim_row():
    run = parse_sample(northfield, "northfield_gl.pdf")
    assert run.claims[3] == Claim(
        carrier="Northfield Mutual Insurance Company",
        insured_name="Brightwater Brewing Company LLC",
        policy_number="NGL-204418-24",
        policy_period_start=date(2024, 1, 1),
        policy_period_end=date(2025, 1, 1),
        line_of_coverage="GL",
        claim_number="NGL-24-00318",
        date_of_loss=date(2024, 6, 7),
        status="open",
        paid=Decimal("28750.00"),
        reserved=Decimal("46250.00"),
        incurred=Decimal("75000.00"),
        valuation_date=date(2026, 9, 18),
        source_file="northfield_gl.pdf",
        source_page=1,
    )


def test_northfield_keeps_policy_term_with_no_claims():
    run = parse_sample(northfield, "northfield_gl.pdf")
    assert "NGL-204418-26" in [t.policy_number for t in run.terms]


def test_harborline_parses_a_claim_row():
    run = parse_sample(harborline, "harborline_wc.pdf")
    assert run.claims[6] == Claim(
        carrier="Harborline Casualty Group",
        insured_name="BRIGHTWATER BREWING COMPANY LLC",
        policy_number="HWC-77120-24",
        policy_period_start=date(2024, 7, 1),
        policy_period_end=date(2025, 7, 1),
        line_of_coverage="WC",
        claim_number="HWC240311",
        date_of_loss=date(2024, 12, 5),
        status="open",
        paid=Decimal("18450.00"),
        reserved=Decimal("6500.00"),
        incurred=Decimal("25950.00"),
        valuation_date=date(2026, 9, 30),
        source_file="harborline_wc.pdf",
        source_page=1,
    )


def test_harborline_policy_year_continues_onto_the_next_page():
    run = parse_sample(harborline, "harborline_wc.pdf")
    pages = [c.source_page for c in run.claims if c.policy_number == "HWC-77120-25"]
    assert pages == [1, 2, 2, 2]


def test_pinecrest_parses_a_claim_row():
    run = parse_sample(pinecrest, "pinecrest_property.pdf")
    assert run.claims[2] == Claim(
        carrier="Pinecrest Specialty Underwriters",
        insured_name="Brightwater Brewing Co.",
        policy_number="PSU-PR-30981-25",
        policy_period_start=date(2025, 6, 1),
        policy_period_end=date(2026, 6, 1),
        line_of_coverage="property",
        claim_number="PSU-C-2025-0218",
        date_of_loss=date(2025, 9, 3),
        status="open",
        paid=Decimal("60000.00"),
        reserved=Decimal("85000.00"),
        incurred=Decimal("145000.00"),
        valuation_date=date(2026, 9, 25),
        source_file="pinecrest_property.pdf",
        source_page=1,
    )


def test_keystone_parses_a_claim_row():
    run = parse_sample(keystone, "keystone_gl_letter.pdf")
    assert run.claims[2] == Claim(
        carrier="Keystone Claims Administrators",
        insured_name="Brightwater Brewing Company LLC",
        policy_number="NGL-204418-25",
        policy_period_start=date(2025, 1, 1),
        policy_period_end=date(2026, 1, 1),
        line_of_coverage="GL",
        claim_number="KCA-118204",
        date_of_loss=date(2025, 2, 15),
        status="open",
        paid=Decimal("2500.00"),
        reserved=Decimal("22500.00"),
        incurred=Decimal("25000.00"),
        valuation_date=date(2026, 5, 29),
        source_file="keystone_gl_letter.pdf",
        source_page=1,
    )


@pytest.mark.parametrize(
    ("parser", "name", "claims", "terms"),
    [
        (northfield, "northfield_gl.pdf", 7, 5),
        (harborline, "harborline_wc.pdf", 13, 6),
        (pinecrest, "pinecrest_property.pdf", 4, 6),
        (keystone, "keystone_gl_letter.pdf", 3, 2),
    ],
)
def test_parser_finds_every_claim_and_term(parser, name, claims, terms):
    run = parse_sample(parser, name)
    assert (len(run.claims), len(run.terms)) == (claims, terms)

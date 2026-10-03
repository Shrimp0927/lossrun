from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from helpers import SAMPLES
from reportlab.pdfgen import canvas

from lossrun.extract import (
    ClaudeAnswer,
    ClaudeClaim,
    ClaudeTerm,
    ExtractionError,
    ask_claude,
    extract_file,
    locate,
)
from lossrun.parsers import northfield
from lossrun.parsers.base import ParseError

PAGES = [
    "ACME INDEMNITY - Auto loss run - Policy ACM-555",
    "Claim ACM-C-9 loss 05/05/2025 open paid 1,000.00 reserve 2,500.50",
]


class FakeClient:
    """Stands in for anthropic.Anthropic: returns a canned parsed answer."""

    def __init__(self, answer, stop_reason="end_turn"):
        self.calls = []
        self.response = SimpleNamespace(stop_reason=stop_reason, parsed_output=answer)
        self.messages = SimpleNamespace(parse=self.parse)

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def make_claude_claim(**overrides) -> ClaudeClaim:
    fields = dict(
        policy_number="ACM-555",
        claim_number="ACM-C-9",
        date_of_loss=date(2025, 5, 5),
        status="open",
        paid="1000.00",
        reserved="2500.50",
        incurred="3500.50",
        source_page=2,
    )
    return ClaudeClaim(**(fields | overrides))


def make_answer(**overrides) -> ClaudeAnswer:
    fields = dict(
        carrier="Acme Indemnity",
        insured_name="Brightwater Brewing Co.",
        valuation_date=date(2026, 9, 1),
        policy_terms=[
            ClaudeTerm(
                policy_number="ACM-555",
                policy_period_start=date(2025, 1, 1),
                policy_period_end=date(2026, 1, 1),
                line_of_coverage="auto",
                source_page=1,
            )
        ],
        claims=[make_claude_claim()],
    )
    return ClaudeAnswer(**(fields | overrides))


def run_claude(answer, stop_reason="end_turn"):
    return ask_claude("acme.pdf", PAGES, "no parser", FakeClient(answer, stop_reason))


def write_pdf(path, *page_lines):
    c = canvas.Canvas(str(path))
    for line in page_lines:
        c.drawString(72, 720, line)
        c.showPage()
    c.save()
    return path


def test_locate_keeps_the_page_when_the_number_is_on_it():
    assert locate("ACM-C-9", 2, PAGES, "claim") == 2


def test_locate_corrects_a_wrong_page():
    assert locate("ACM-C-9", 1, PAGES, "claim") == 2


def test_locate_rejects_a_number_that_is_not_in_the_document():
    with pytest.raises(ExtractionError, match="ACM-C-404.*not in the document"):
        locate("ACM-C-404", 1, PAGES, "claim")


def test_ask_claude_sends_every_page_to_the_model():
    client = FakeClient(make_answer())
    ask_claude("acme.pdf", PAGES, "no parser", client)
    assert '<page number="2">' in client.calls[0]["messages"][0]["content"]


def test_ask_claude_converts_amounts_to_decimals():
    [claim] = run_claude(make_answer()).claims
    assert (claim.paid, claim.reserved, claim.incurred) == (
        Decimal("1000.00"),
        Decimal("2500.50"),
        Decimal("3500.50"),
    )


def test_ask_claude_fills_claim_from_its_policy_term():
    [claim] = run_claude(make_answer()).claims
    assert (claim.line_of_coverage, claim.policy_period_end) == ("auto", date(2026, 1, 1))


def test_ask_claude_records_why_the_parser_was_not_used():
    run = run_claude(make_answer())
    assert (run.method, run.method_detail) == ("claude", "no parser")


def test_ask_claude_rejects_claim_on_unlisted_policy():
    answer = make_answer(claims=[make_claude_claim(policy_number="ACM-999")])
    with pytest.raises(ExtractionError, match="unlisted policy ACM-999"):
        run_claude(answer)


def test_ask_claude_rejects_amount_that_is_not_a_number():
    answer = make_answer(claims=[make_claude_claim(paid="n/a")])
    with pytest.raises(ExtractionError, match="not a number"):
        run_claude(answer)


def test_ask_claude_rejects_answer_without_policy_terms():
    with pytest.raises(ExtractionError, match="no policy terms"):
        run_claude(make_answer(policy_terms=[], claims=[]))


def test_ask_claude_rejects_truncated_answer():
    with pytest.raises(ExtractionError, match="max_tokens"):
        run_claude(None, stop_reason="max_tokens")


def test_extract_file_uses_the_carrier_parser():
    run = extract_file(SAMPLES / "northfield_gl.pdf")
    assert (run.method, run.method_detail) == ("parser", "northfield")


def test_extract_file_sends_unknown_carrier_to_claude(tmp_path):
    path = write_pdf(tmp_path / "acme.pdf", *PAGES)
    run = extract_file(path, FakeClient(make_answer()))
    assert (run.method, run.method_detail) == ("claude", "no carrier parser matched the header")


def test_extract_file_asks_claude_when_the_parser_fails(monkeypatch):
    def broken(pdf, source_file):
        raise ParseError("totals do not match")

    monkeypatch.setattr(northfield, "parse", broken)
    answer = make_answer(
        policy_terms=[
            ClaudeTerm(
                policy_number="NGL-204418-21",
                policy_period_start=date(2021, 1, 1),
                policy_period_end=date(2022, 1, 1),
                line_of_coverage="GL",
                source_page=1,
            )
        ],
        claims=[],
    )
    run = extract_file(SAMPLES / "northfield_gl.pdf", FakeClient(answer))
    assert (run.method, run.method_detail) == (
        "claude",
        "northfield parser failed: totals do not match",
    )


def test_extract_file_reports_both_reasons_when_claude_also_fails(tmp_path):
    path = write_pdf(tmp_path / "acme.pdf", *PAGES)
    with pytest.raises(ExtractionError, match="no carrier parser matched.*Claude also failed"):
        extract_file(path, FakeClient(None, stop_reason="max_tokens"))


def test_extract_file_rejects_pdf_without_text(tmp_path):
    path = write_pdf(tmp_path / "scan.pdf", "")
    with pytest.raises(ExtractionError, match="no text in it"):
        extract_file(path, FakeClient(make_answer()))

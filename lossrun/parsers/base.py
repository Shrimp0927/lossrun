"""Shared pieces for per-carrier parsers.

Parsers are strict: anything unexpected (unknown row, a total that does not
match the rows read) raises ParseError, so the file is read by Claude instead
of producing a quietly wrong table.
"""

import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pdfplumber

from lossrun.models import Claim, ClaimStatus, LineOfCoverage, LossRun, PolicyTerm


class ParseError(Exception):
    """The report did not match the layout this parser expects."""


def money(text: str) -> Decimal:
    """'$12,400.00' -> Decimal('12400.00'); '(150.00)' -> Decimal('-150.00')."""
    cleaned = text.strip().replace("$", "").replace(",", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParseError(f"not an amount: {text!r}") from exc


def parse_date(text: str, date_format: str) -> date:
    try:
        return datetime.strptime(text.strip(), date_format).date()
    except ValueError as exc:
        raise ParseError(f"not a date ({date_format}): {text!r}") from exc


def search(pattern: str, text: str, what: str) -> re.Match[str]:
    match = re.search(pattern, text)
    if match is None:
        raise ParseError(f"could not find {what}")
    return match


def check_equal(what: str, parsed: object, printed: object) -> None:
    if parsed != printed:
        raise ParseError(f"{what}: parsed {parsed} but report prints {printed}")


def table_rows(pdf: pdfplumber.PDF) -> Iterator[tuple[int, list[str]]]:
    """Every table row in the PDF as (page number, cell texts)."""
    for page_no, page in enumerate(pdf.pages, start=1):
        for table in page.extract_tables():
            for row in table:
                yield page_no, [(cell or "").strip() for cell in row]


class RunBuilder:
    """Collects the terms and claims of one file and fills in the fields they share."""

    def __init__(
        self,
        *,
        source_file: str,
        parser_name: str,
        carrier: str,
        insured_name: str,
        line: LineOfCoverage,
        valuation_date: date,
        page_count: int,
    ) -> None:
        self.parser_name = parser_name
        self.page_count = page_count
        self.line = line
        self.common = dict(
            carrier=carrier,
            insured_name=insured_name,
            valuation_date=valuation_date,
            source_file=source_file,
        )
        self.terms: dict[str, PolicyTerm] = {}
        self.claims: list[Claim] = []

    def term(self, policy_number: str, start: date, end: date, page: int) -> None:
        """Register a policy term; repeats (one per claim row, say) are fine."""
        existing = self.terms.get(policy_number)
        if existing is None:
            self.terms[policy_number] = PolicyTerm(
                policy_number=policy_number,
                policy_period_start=start,
                policy_period_end=end,
                line_of_coverage=self.line,
                source_page=page,
                **self.common,
            )
        elif (existing.policy_period_start, existing.policy_period_end) != (start, end):
            raise ParseError(f"policy {policy_number} appears with two different periods")

    def claim(
        self,
        *,
        policy_number: str,
        claim_number: str,
        date_of_loss: date,
        status: str,
        paid: str,
        reserved: str,
        incurred: str,
        page: int,
    ) -> None:
        term = self.terms.get(policy_number)
        if term is None:
            raise ParseError(f"claim {claim_number} references unknown policy {policy_number}")
        self.claims.append(
            Claim(
                policy_number=policy_number,
                policy_period_start=term.policy_period_start,
                policy_period_end=term.policy_period_end,
                line_of_coverage=self.line,
                claim_number=claim_number,
                date_of_loss=date_of_loss,
                status=ClaimStatus.parse(status),
                paid=money(paid),
                reserved=money(reserved),
                incurred=money(incurred),
                source_page=page,
                **self.common,
            )
        )

    def claims_for(self, policy_number: str) -> list[Claim]:
        return [c for c in self.claims if c.policy_number == policy_number]

    def check_totals(
        self, what: str, claims: list[Claim], *, count: int, paid: str, reserved: str, incurred: str
    ) -> None:
        """Compare the rows read against a total line the carrier printed."""
        check_equal(f"{what} claim count", len(claims), count)
        for field, printed in (("paid", paid), ("reserved", reserved), ("incurred", incurred)):
            parsed = sum((getattr(c, field) for c in claims), Decimal(0))
            check_equal(f"{what} {field}", parsed, money(printed))

    def build(self) -> LossRun:
        if not self.terms:
            raise ParseError("no policy terms found")
        return LossRun(
            method="parser",
            method_detail=self.parser_name,
            page_count=self.page_count,
            terms=list(self.terms.values()),
            claims=self.claims,
            **self.common,
        )

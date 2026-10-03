"""PDF -> LossRun: try the carrier parser first, then ask Claude."""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import anthropic
import pdfplumber
from pydantic import BaseModel, Field

from lossrun.models import Claim, ClaimStatus, LineOfCoverage, LossRun, PolicyTerm
from lossrun.parsers.registry import detect_parser

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You extract insurance loss-run reports into structured data for a broker who \
will compare them with other carriers' reports. The text of each page is \
given inside <page number="N"> tags.

Transcribe what the report prints; do not correct or compute anything:
- Report paid, reserved and incurred exactly as printed, even if incurred does \
not equal paid plus reserved. The broker needs to see such discrepancies.
- One entry per claim. Skip subtotal, total and summary rows.
- List every policy term the report covers in policy_terms, including terms \
with no claims.
- Each claim's policy_number must be one of the listed policy terms.
- valuation_date is the date the figures are valued as of, not the date the \
report was run or the letter was written.
- carrier is the organization that issued the report.
- source_page is the page number the claim or term appears on.
- Amounts are plain decimal strings such as "12400.00": no currency symbol, \
no thousands separators. Amounts in parentheses are negative.
- Dates are written YYYY-MM-DD.
If the document is not a loss run, return empty policy_terms and claims."""


class ExtractionError(Exception):
    """Neither a carrier parser nor Claude could read the file."""


class ClaudeTerm(BaseModel):
    policy_number: str
    policy_period_start: date
    policy_period_end: date
    line_of_coverage: Literal["GL", "WC", "auto", "property"]
    source_page: int


class ClaudeClaim(BaseModel):
    policy_number: str
    claim_number: str
    date_of_loss: date
    status: Literal["open", "closed"]
    paid: str = Field(description='Decimal string as printed, e.g. "12400.00"')
    reserved: str = Field(description='Decimal string as printed, e.g. "0.00"')
    incurred: str = Field(description='Decimal string as printed, e.g. "12400.00"')
    source_page: int


class ClaudeAnswer(BaseModel):
    carrier: str
    insured_name: str
    valuation_date: date
    policy_terms: list[ClaudeTerm]
    claims: list[ClaudeClaim]


def extract_file(path: Path, client: anthropic.Anthropic | None = None) -> LossRun:
    """Read one PDF. Raises ExtractionError if neither the parser nor Claude can read it."""
    with pdfplumber.open(path) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]
        if not any(text.strip() for text in page_texts):
            raise ExtractionError(
                "the PDF has no text in it (a scan?); scanned pages cannot be read"
            )

        parser = detect_parser(page_texts[0])
        if parser is None:
            reason = "no carrier parser matched the header"
        else:
            try:
                return parser.parse(pdf, path.name)
            # Whatever went wrong, the layout was not what the parser expects.
            except Exception as exc:
                reason = f"{parser.NAME} parser failed: {exc}"

    try:
        return ask_claude(path.name, page_texts, reason, client)
    except ExtractionError as exc:
        raise ExtractionError(f"{reason}; Claude also failed: {exc}") from exc


def ask_claude(
    source_file: str,
    page_texts: list[str],
    reason: str,
    client: anthropic.Anthropic | None = None,
) -> LossRun:
    document = "\n".join(
        f'<page number="{n}">\n{text}\n</page>' for n, text in enumerate(page_texts, start=1)
    )
    try:
        client = client or anthropic.Anthropic()
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": document}],
            output_format=ClaudeAnswer,
        )
    # The SDK raises TypeError when it has no credentials at all.
    except (anthropic.AnthropicError, TypeError) as exc:
        raise ExtractionError(f"the request to Claude failed: {exc}") from exc

    if response.stop_reason != "end_turn" or response.parsed_output is None:
        raise ExtractionError(f"model stopped without a complete answer ({response.stop_reason})")
    return to_loss_run(response.parsed_output, source_file, page_texts, reason)


def to_loss_run(
    data: ClaudeAnswer, source_file: str, page_texts: list[str], reason: str
) -> LossRun:
    """Turn Claude's answer into a LossRun, checking it against the page text."""
    if not data.policy_terms:
        raise ExtractionError("model found no policy terms; not a loss run?")

    common = dict(
        carrier=data.carrier,
        insured_name=data.insured_name,
        valuation_date=data.valuation_date,
        source_file=source_file,
    )
    terms = {
        t.policy_number: PolicyTerm(
            policy_number=t.policy_number,
            policy_period_start=t.policy_period_start,
            policy_period_end=t.policy_period_end,
            line_of_coverage=LineOfCoverage(t.line_of_coverage),
            source_page=locate(t.policy_number, t.source_page, page_texts, "policy"),
            **common,
        )
        for t in data.policy_terms
    }

    claims = []
    for c in data.claims:
        term = terms.get(c.policy_number)
        if term is None:
            raise ExtractionError(
                f"claim {c.claim_number} references unlisted policy {c.policy_number}"
            )
        try:
            paid, reserved, incurred = Decimal(c.paid), Decimal(c.reserved), Decimal(c.incurred)
        except InvalidOperation as exc:
            raise ExtractionError(f"claim {c.claim_number}: amount is not a number") from exc
        claims.append(
            Claim(
                policy_number=c.policy_number,
                policy_period_start=term.policy_period_start,
                policy_period_end=term.policy_period_end,
                line_of_coverage=term.line_of_coverage,
                claim_number=c.claim_number,
                date_of_loss=c.date_of_loss,
                status=ClaimStatus(c.status),
                paid=paid,
                reserved=reserved,
                incurred=incurred,
                source_page=locate(c.claim_number, c.source_page, page_texts, "claim"),
                **common,
            )
        )
    return LossRun(
        method="claude",
        method_detail=reason,
        page_count=len(page_texts),
        terms=list(terms.values()),
        claims=claims,
        **common,
    )


def locate(number: str, claimed_page: int, page_texts: list[str], what: str) -> int:
    """Return the page a claim or policy number is printed on.

    Guards against invented rows: every claim and policy number the model
    returns must appear word for word in the document.
    """
    if 1 <= claimed_page <= len(page_texts) and number in page_texts[claimed_page - 1]:
        return claimed_page
    for page_no, text in enumerate(page_texts, start=1):
        if number in text:
            return page_no
    raise ExtractionError(f"model returned {what} number {number!r}, which is not in the document")

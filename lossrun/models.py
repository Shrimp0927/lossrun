"""The data shapes every step shares."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

# Decimal in Python, plain number in JSON output.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class LineOfCoverage(StrEnum):
    GL = "GL"
    WC = "WC"
    AUTO = "auto"
    PROPERTY = "property"

    @classmethod
    def parse(cls, text: str) -> "LineOfCoverage":
        key = text.strip().lower()
        if key not in LINE_ALIASES:
            raise ValueError(f"unknown line of coverage: {text!r}")
        return LINE_ALIASES[key]


LINE_ALIASES = {
    "gl": LineOfCoverage.GL,
    "general liability": LineOfCoverage.GL,
    "commercial general liability": LineOfCoverage.GL,
    "wc": LineOfCoverage.WC,
    "workers compensation": LineOfCoverage.WC,
    "workers' compensation": LineOfCoverage.WC,
    "auto": LineOfCoverage.AUTO,
    "commercial auto": LineOfCoverage.AUTO,
    "business auto": LineOfCoverage.AUTO,
    "property": LineOfCoverage.PROPERTY,
    "commercial property": LineOfCoverage.PROPERTY,
}


class ClaimStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"

    @classmethod
    def parse(cls, text: str) -> "ClaimStatus":
        key = text.strip().lower()
        if key not in STATUS_ALIASES:
            raise ValueError(f"unknown claim status: {text!r}")
        return STATUS_ALIASES[key]


STATUS_ALIASES = {
    "open": ClaimStatus.OPEN,
    "o": ClaimStatus.OPEN,
    "reopened": ClaimStatus.OPEN,
    "re-opened": ClaimStatus.OPEN,
    "closed": ClaimStatus.CLOSED,
    "c": ClaimStatus.CLOSED,
}


class Claim(BaseModel):
    carrier: str
    insured_name: str
    policy_number: str
    policy_period_start: date
    policy_period_end: date
    line_of_coverage: LineOfCoverage
    claim_number: str
    date_of_loss: date
    status: ClaimStatus
    paid: Money
    reserved: Money
    incurred: Money
    valuation_date: date
    source_file: str
    source_page: int


class PolicyTerm(BaseModel):
    """A policy period a report covers. A clean year has no claims but still counts as coverage."""

    carrier: str
    insured_name: str
    policy_number: str
    policy_period_start: date
    policy_period_end: date
    line_of_coverage: LineOfCoverage
    valuation_date: date
    source_file: str
    source_page: int


ExtractionMethod = Literal["parser", "claude"]


class LossRun(BaseModel):
    """Everything extracted from one PDF."""

    source_file: str
    carrier: str
    insured_name: str
    valuation_date: date
    method: ExtractionMethod
    # Parser name, or why Claude read the file instead.
    method_detail: str = ""
    page_count: int
    terms: list[PolicyTerm]
    claims: list[Claim]


class SourceInfo(BaseModel):
    """How one input file was handled."""

    source_file: str
    carrier: str | None = None
    method: ExtractionMethod | Literal["failed"]
    detail: str = ""
    valuation_date: date | None = None
    page_count: int | None = None
    claim_count: int = 0


class PolicySummary(BaseModel):
    line_of_coverage: LineOfCoverage
    carrier: str
    insured_name: str
    policy_number: str
    policy_period_start: date
    policy_period_end: date
    claim_count: int
    open_count: int
    paid: Money
    reserved: Money
    incurred: Money
    valuation_date: date
    source_files: list[str]


class FlagCode(StrEnum):
    STALE_VALUATION = "STALE_VALUATION"
    OPEN_RESERVE = "OPEN_RESERVE"
    DUPLICATE_CLAIM_NUMBER = "DUPLICATE_CLAIM_NUMBER"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    MISSING_LINE = "MISSING_LINE"
    COVERAGE_GAP = "COVERAGE_GAP"
    INCURRED_MISMATCH = "INCURRED_MISMATCH"


class Flag(BaseModel):
    code: FlagCode
    line_of_coverage: LineOfCoverage | None = None
    policy_number: str | None = None
    claim_number: str | None = None
    source_file: str | None = None
    source_page: int | None = None
    message: str


class Report(BaseModel):
    as_of: date
    files: list[SourceInfo]
    claims: list[Claim]
    summary: list[PolicySummary]
    flags: list[Flag]

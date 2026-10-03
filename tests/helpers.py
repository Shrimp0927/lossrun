from datetime import date
from decimal import Decimal
from pathlib import Path

from lossrun.models import Claim, ClaimStatus, LineOfCoverage, LossRun, PolicyTerm

SAMPLES = Path(__file__).parent.parent / "samples"
AS_OF = date(2026, 10, 2)


def make_term(
    policy="P-1",
    start=date(2025, 1, 1),
    end=date(2026, 1, 1),
    *,
    line=LineOfCoverage.GL,
    file="a.pdf",
    valuation=date(2026, 9, 1),
) -> PolicyTerm:
    return PolicyTerm(
        carrier="Carrier",
        insured_name="Insured",
        policy_number=policy,
        policy_period_start=start,
        policy_period_end=end,
        line_of_coverage=line,
        valuation_date=valuation,
        source_file=file,
        source_page=1,
    )


def make_claim(
    number="C-1",
    *,
    policy="P-1",
    loss_date=date(2025, 3, 1),
    status="closed",
    paid="100.00",
    reserved="0.00",
    incurred=None,
    line=LineOfCoverage.GL,
    file="a.pdf",
    valuation=date(2026, 9, 1),
) -> Claim:
    """incurred defaults to paid + reserved."""
    return Claim(
        carrier="Carrier",
        insured_name="Insured",
        policy_number=policy,
        policy_period_start=date(2025, 1, 1),
        policy_period_end=date(2026, 1, 1),
        line_of_coverage=line,
        claim_number=number,
        date_of_loss=loss_date,
        status=ClaimStatus(status),
        paid=Decimal(paid),
        reserved=Decimal(reserved),
        incurred=Decimal(incurred or Decimal(paid) + Decimal(reserved)),
        valuation_date=valuation,
        source_file=file,
        source_page=1,
    )


def make_run(file="a.pdf", *, terms=(), claims=(), valuation=date(2026, 9, 1)) -> LossRun:
    return LossRun(
        source_file=file,
        carrier="Carrier",
        insured_name="Insured",
        valuation_date=valuation,
        method="parser",
        page_count=1,
        terms=list(terms),
        claims=list(claims),
    )

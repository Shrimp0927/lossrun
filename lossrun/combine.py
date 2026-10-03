"""Merge what was read from each file into one claims table and a summary per policy."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from lossrun.models import Claim, LossRun, PolicySummary, PolicyTerm

PolicyKey = tuple[str, date]


def merge_claims(runs: list[LossRun]) -> list[Claim]:
    """Every claim row from every file. Duplicates are kept and flagged, never dropped."""
    claims = [claim for run in runs for claim in run.claims]
    return sorted(
        claims,
        key=lambda c: (
            c.line_of_coverage.value,
            c.policy_period_start,
            c.policy_number,
            c.date_of_loss,
            c.claim_number,
            c.source_file,
        ),
    )


def summarize(runs: list[LossRun]) -> list[PolicySummary]:
    """One row per policy term, including terms with no claims.

    A claim number reported by several files counts once, using the most
    recently valued row.
    """
    terms: dict[PolicyKey, list[PolicyTerm]] = defaultdict(list)
    latest: dict[PolicyKey, dict[str, Claim]] = defaultdict(dict)
    for run in runs:
        for term in run.terms:
            terms[(term.policy_number, term.policy_period_start)].append(term)
        for claim in run.claims:
            by_number = latest[(claim.policy_number, claim.policy_period_start)]
            current = by_number.get(claim.claim_number)
            if current is None or claim.valuation_date > current.valuation_date:
                by_number[claim.claim_number] = claim

    summaries = []
    for key, reported in terms.items():
        newest = max(reported, key=lambda t: t.valuation_date)
        claims = list(latest[key].values())
        summaries.append(
            PolicySummary(
                line_of_coverage=newest.line_of_coverage,
                carrier=newest.carrier,
                insured_name=newest.insured_name,
                policy_number=newest.policy_number,
                policy_period_start=newest.policy_period_start,
                policy_period_end=newest.policy_period_end,
                claim_count=len(claims),
                open_count=sum(1 for c in claims if c.status == "open"),
                paid=sum((c.paid for c in claims), Decimal("0.00")),
                reserved=sum((c.reserved for c in claims), Decimal("0.00")),
                incurred=sum((c.incurred for c in claims), Decimal("0.00")),
                valuation_date=newest.valuation_date,
                source_files=sorted({t.source_file for t in reported}),
            )
        )
    return sorted(
        summaries, key=lambda s: (s.line_of_coverage.value, s.policy_period_start, s.policy_number)
    )

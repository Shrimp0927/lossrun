"""Checks a broker would otherwise do by hand. Each flag comes with a one-line explanation."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from lossrun.models import Claim, Flag, FlagCode, LineOfCoverage, LossRun, PolicyTerm

STALE_AFTER_DAYS = 90


def build_flags(
    runs: list[LossRun],
    *,
    as_of: date,
    required_lines: list[LineOfCoverage] | None = None,
    years: int = 5,
) -> list[Flag]:
    claims = sorted(
        (claim for run in runs for claim in run.claims),
        key=lambda c: (c.line_of_coverage.value, c.date_of_loss, c.claim_number, c.source_file),
    )
    terms = [term for run in runs for term in run.terms]
    return [
        *stale_valuations(runs, as_of),
        *open_reserves(claims),
        *duplicate_claim_numbers(claims),
        *possible_duplicates(claims),
        *missing_lines(terms, required_lines or []),
        *coverage_gaps(terms, as_of, years, required_lines),
        *incurred_mismatches(claims),
    ]


def dollars(amount: Decimal) -> str:
    return f"-${-amount:,.2f}" if amount < 0 else f"${amount:,.2f}"


def where(claim: Claim) -> str:
    return f"{claim.source_file} p{claim.source_page}"


def claim_flag(code: FlagCode, claim: Claim, message: str) -> Flag:
    return Flag(
        code=code,
        line_of_coverage=claim.line_of_coverage,
        policy_number=claim.policy_number,
        claim_number=claim.claim_number,
        source_file=claim.source_file,
        source_page=claim.source_page,
        message=message,
    )


def stale_valuations(runs: list[LossRun], as_of: date) -> list[Flag]:
    flags = []
    for run in runs:
        age = (as_of - run.valuation_date).days
        if age <= STALE_AFTER_DAYS:
            continue
        lines = {t.line_of_coverage for t in run.terms}
        flags.append(
            Flag(
                code=FlagCode.STALE_VALUATION,
                line_of_coverage=lines.pop() if len(lines) == 1 else None,
                policy_number=", ".join(sorted({t.policy_number for t in run.terms})),
                source_file=run.source_file,
                message=(
                    f"{run.carrier} report is valued {run.valuation_date}, {age} days before "
                    f"{as_of} (limit {STALE_AFTER_DAYS}); request a current loss run."
                ),
            )
        )
    return flags


def open_reserves(claims: list[Claim]) -> list[Flag]:
    return [
        claim_flag(
            FlagCode.OPEN_RESERVE,
            c,
            f"Open claim with {dollars(c.reserved)} still reserved (paid {dollars(c.paid)}, "
            f"incurred {dollars(c.incurred)}, loss date {c.date_of_loss}).",
        )
        for c in claims
        if c.status == "open" and c.reserved != 0
    ]


def duplicate_claim_numbers(claims: list[Claim]) -> list[Flag]:
    """Same claim number in more than one file. One flag per claim number."""
    by_number: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        by_number[claim.claim_number].append(claim)

    flags = []
    for number, group in by_number.items():
        if len({c.source_file for c in group}) < 2:
            continue
        group = sorted(group, key=lambda c: c.valuation_date, reverse=True)
        seen = "; ".join(
            f"{where(c)} (incurred {dollars(c.incurred)}, valued {c.valuation_date})" for c in group
        )
        if len({(c.paid, c.reserved, c.incurred, c.status) for c in group}) == 1:
            verdict = "figures match"
        else:
            verdict = "figures differ, the latest valuation is used in the summary"
        flags.append(
            claim_flag(
                FlagCode.DUPLICATE_CLAIM_NUMBER,
                group[0],
                f"Claim {number} appears in {len(group)} files: {seen}; {verdict}.",
            )
        )
    return flags


def possible_duplicates(claims: list[Claim]) -> list[Flag]:
    """Different claim numbers, different files, same (date of loss, line, incurred)."""
    by_loss: dict[tuple[date, LineOfCoverage, Decimal], list[Claim]] = defaultdict(list)
    for claim in claims:
        by_loss[(claim.date_of_loss, claim.line_of_coverage, claim.incurred)].append(claim)

    flags = []
    for (loss_date, line, incurred), group in by_loss.items():
        distinct = {c.claim_number: c for c in group}
        if len(distinct) < 2 or len({c.source_file for c in distinct.values()}) < 2:
            continue
        members = sorted(distinct.values(), key=lambda c: (c.source_file, c.claim_number))
        listed = " and ".join(f"{c.claim_number} ({where(c)})" for c in members)
        flags.append(
            claim_flag(
                FlagCode.POSSIBLE_DUPLICATE,
                members[0],
                f"{listed} share loss date {loss_date}, line {line.value} "
                f"and incurred {dollars(incurred)}; "
                "likely the same claim under two numbers, and both are counted in the summary.",
            )
        )
    return flags


def missing_lines(terms: list[PolicyTerm], required: list[LineOfCoverage]) -> list[Flag]:
    present = {t.line_of_coverage for t in terms}
    return [
        Flag(
            code=FlagCode.MISSING_LINE,
            line_of_coverage=line,
            message=(
                f"{line.value} was requested with --lines "
                f"but no {line.value} loss run is in this set."
            ),
        )
        for line in required
        if line not in present
    ]


def window_start(as_of: date, years: int) -> date:
    try:
        return as_of.replace(year=as_of.year - years)
    except ValueError:  # Feb 29 in a non-leap target year
        return as_of.replace(year=as_of.year - years, day=28)


def coverage_gaps(
    terms: list[PolicyTerm],
    as_of: date,
    years: int,
    required: list[LineOfCoverage] | None = None,
) -> list[Flag]:
    """Stretches of the last `years` years not covered by any reported policy period.

    Periods are [start, end): a policy ending 01/01 and one starting 01/01 are
    continuous. Lines with no report at all are left to MISSING_LINE.
    """
    by_line: dict[LineOfCoverage, list[PolicyTerm]] = defaultdict(list)
    for term in terms:
        by_line[term.line_of_coverage].append(term)

    flags = []
    for line, line_terms in by_line.items():
        if required and line not in required:
            continue
        covered_to = window_start(as_of, years)
        previous = None
        for term in sorted(line_terms, key=lambda t: t.policy_period_start):
            if term.policy_period_start > covered_to and covered_to < as_of:
                gap_end = min(term.policy_period_start, as_of)
                flags.append(gap_flag(line, covered_to, gap_end, previous, term, as_of, years))
            if term.policy_period_end > covered_to:
                covered_to, previous = term.policy_period_end, term
        if covered_to < as_of:
            flags.append(gap_flag(line, covered_to, as_of, previous, None, as_of, years))
    return flags


def gap_flag(
    line: LineOfCoverage,
    start: date,
    end: date,
    before: PolicyTerm | None,
    after: PolicyTerm | None,
    as_of: date,
    years: int,
) -> Flag:
    if before and after:
        position = f"between {before.policy_number} and {after.policy_number}"
    elif after:
        position = f"before {after.policy_number}"
    elif before:
        position = f"after {before.policy_number}"
    else:
        position = "no policy covers these years"
    neighbor = before or after
    return Flag(
        code=FlagCode.COVERAGE_GAP,
        line_of_coverage=line,
        policy_number=neighbor.policy_number if neighbor else None,
        source_file=neighbor.source_file if neighbor else None,
        source_page=neighbor.source_page if neighbor else None,
        message=(
            f"No {line.value} policy period reported from {start} to {end} "
            f"({(end - start).days} days, {position}) "
            f"in the {years} years before {as_of}."
        ),
    )


def incurred_mismatches(claims: list[Claim]) -> list[Flag]:
    return [
        claim_flag(
            FlagCode.INCURRED_MISMATCH,
            c,
            f"Incurred {dollars(c.incurred)} does not equal paid {dollars(c.paid)} + reserved "
            f"{dollars(c.reserved)} = {dollars(c.paid + c.reserved)} "
            f"(off by {dollars(c.incurred - c.paid - c.reserved)}).",
        )
        for c in claims
        if c.incurred != c.paid + c.reserved
    ]

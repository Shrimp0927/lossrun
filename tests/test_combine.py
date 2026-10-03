from datetime import date
from decimal import Decimal

from helpers import make_claim, make_run, make_term

from lossrun.combine import merge_claims, summarize
from lossrun.models import LineOfCoverage


def test_merge_keeps_a_claim_reported_by_two_files_as_two_rows():
    runs = [
        make_run("a.pdf", claims=[make_claim("C-1", file="a.pdf")]),
        make_run("b.pdf", claims=[make_claim("C-1", file="b.pdf")]),
    ]
    assert [c.source_file for c in merge_claims(runs)] == ["a.pdf", "b.pdf"]


def test_merge_sorts_by_line_then_date_of_loss():
    run = make_run(
        claims=[
            make_claim("WC-1", line=LineOfCoverage.WC, loss_date=date(2025, 1, 1)),
            make_claim("GL-2", line=LineOfCoverage.GL, loss_date=date(2025, 6, 1)),
            make_claim("GL-1", line=LineOfCoverage.GL, loss_date=date(2025, 2, 1)),
        ]
    )
    assert [c.claim_number for c in merge_claims([run])] == ["GL-1", "GL-2", "WC-1"]


def test_summary_totals_the_claims_of_a_policy_term():
    run = make_run(
        terms=[make_term()],
        claims=[
            make_claim("C-1", status="open", paid="100.00", reserved="50.00"),
            make_claim("C-2", status="closed", paid="25.00"),
        ],
    )
    [row] = summarize([run])
    assert (row.claim_count, row.open_count, row.paid, row.reserved, row.incurred) == (
        2,
        1,
        Decimal("125.00"),
        Decimal("50.00"),
        Decimal("175.00"),
    )


def test_summary_includes_a_term_without_claims():
    [row] = summarize([make_run(terms=[make_term()])])
    assert (row.claim_count, row.incurred) == (0, Decimal("0.00"))


def test_summary_counts_a_claim_reported_twice_once_using_the_latest_valuation():
    old = make_run(
        "old.pdf",
        terms=[make_term(file="old.pdf", valuation=date(2026, 1, 1))],
        claims=[make_claim("C-1", file="old.pdf", valuation=date(2026, 1, 1), paid="10.00")],
    )
    new = make_run(
        "new.pdf",
        terms=[make_term(file="new.pdf", valuation=date(2026, 9, 1))],
        claims=[make_claim("C-1", file="new.pdf", valuation=date(2026, 9, 1), paid="99.00")],
    )
    [row] = summarize([new, old])
    assert (row.claim_count, row.paid, row.valuation_date) == (
        1,
        Decimal("99.00"),
        date(2026, 9, 1),
    )


def test_summary_lists_every_file_that_reported_the_term():
    runs = [
        make_run("a.pdf", terms=[make_term(file="a.pdf")]),
        make_run("b.pdf", terms=[make_term(file="b.pdf")]),
    ]
    [row] = summarize(runs)
    assert row.source_files == ["a.pdf", "b.pdf"]

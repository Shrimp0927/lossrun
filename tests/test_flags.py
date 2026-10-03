from datetime import date, timedelta
from decimal import Decimal

from helpers import AS_OF, make_claim, make_run, make_term

from lossrun.flags import (
    coverage_gaps,
    dollars,
    duplicate_claim_numbers,
    incurred_mismatches,
    missing_lines,
    open_reserves,
    possible_duplicates,
    stale_valuations,
    window_start,
)
from lossrun.models import LineOfCoverage

GL, WC, AUTO = LineOfCoverage.GL, LineOfCoverage.WC, LineOfCoverage.AUTO


def yearly_terms(*years):
    return [make_term(f"P-{y}", date(y, 1, 1), date(y + 1, 1, 1)) for y in years]


def test_dollars_formats_thousands():
    assert dollars(Decimal("12400.5")) == "$12,400.50"


def test_dollars_puts_the_minus_sign_before_the_dollar():
    assert dollars(Decimal(-150)) == "-$150.00"


def test_valuation_90_days_old_is_not_stale():
    run = make_run(valuation=AS_OF - timedelta(days=90), terms=[make_term()])
    assert stale_valuations([run], AS_OF) == []


def test_valuation_91_days_old_is_stale():
    run = make_run(valuation=AS_OF - timedelta(days=91), terms=[make_term()])
    [flag] = stale_valuations([run], AS_OF)
    assert (flag.source_file, flag.policy_number) == ("a.pdf", "P-1")


def test_open_claim_with_a_reserve_is_flagged():
    [flag] = open_reserves([make_claim("C-1", status="open", reserved="500.00")])
    assert flag.claim_number == "C-1"


def test_open_claim_with_zero_reserve_is_not_flagged():
    assert open_reserves([make_claim(status="open", reserved="0.00")]) == []


def test_closed_claim_with_a_reserve_is_not_flagged():
    assert open_reserves([make_claim(status="closed", reserved="500.00")]) == []


def test_same_claim_number_in_two_files_is_one_duplicate():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("C-1", file="b.pdf")]
    [flag] = duplicate_claim_numbers(claims)
    assert flag.claim_number == "C-1"


def test_duplicate_points_at_the_latest_valuation():
    claims = [
        make_claim("C-1", file="old.pdf", valuation=date(2026, 6, 1)),
        make_claim("C-1", file="new.pdf", valuation=date(2026, 9, 1)),
    ]
    [flag] = duplicate_claim_numbers(claims)
    assert flag.source_file == "new.pdf"


def test_duplicate_says_when_figures_differ():
    claims = [
        make_claim("C-1", file="a.pdf", paid="200.00"),
        make_claim("C-1", file="b.pdf", paid="150.00"),
    ]
    [flag] = duplicate_claim_numbers(claims)
    assert "figures differ" in flag.message


def test_duplicate_says_when_figures_match():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("C-1", file="b.pdf")]
    [flag] = duplicate_claim_numbers(claims)
    assert "figures match" in flag.message


def test_same_claim_number_twice_in_one_file_is_not_a_duplicate():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("C-1", file="a.pdf")]
    assert duplicate_claim_numbers(claims) == []


def test_same_loss_under_two_numbers_is_a_possible_duplicate():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("KCA-9", file="b.pdf")]
    [flag] = possible_duplicates(claims)
    assert "C-1" in flag.message and "KCA-9" in flag.message


def test_possible_duplicate_needs_the_same_loss_date():
    claims = [
        make_claim("C-1", file="a.pdf"),
        make_claim("C-2", file="b.pdf", loss_date=date(2025, 3, 2)),
    ]
    assert possible_duplicates(claims) == []


def test_possible_duplicate_needs_the_same_line():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("C-2", file="b.pdf", line=WC)]
    assert possible_duplicates(claims) == []


def test_possible_duplicate_needs_the_same_incurred():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("C-2", file="b.pdf", paid="100.01")]
    assert possible_duplicates(claims) == []


def test_possible_duplicate_needs_two_files():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("C-2", file="a.pdf")]
    assert possible_duplicates(claims) == []


def test_same_claim_number_is_not_a_possible_duplicate():
    claims = [make_claim("C-1", file="a.pdf"), make_claim("C-1", file="b.pdf")]
    assert possible_duplicates(claims) == []


def test_required_line_without_a_report_is_missing():
    [flag] = missing_lines([make_term(line=GL)], [GL, AUTO])
    assert flag.line_of_coverage == AUTO


def test_no_required_lines_means_nothing_is_missing():
    assert missing_lines([make_term(line=GL)], []) == []


def test_term_without_claims_still_counts_as_a_report():
    assert missing_lines([make_term(line=AUTO)], [AUTO]) == []


def test_window_start_is_that_many_years_back():
    assert window_start(AS_OF, 5) == date(2021, 10, 2)


def test_window_start_from_leap_day():
    assert window_start(date(2024, 2, 29), 1) == date(2023, 2, 28)


def test_back_to_back_terms_have_no_gap():
    assert coverage_gaps(yearly_terms(2021, 2022, 2023, 2024, 2025, 2026), AS_OF, 5) == []


def test_gap_in_the_middle():
    [flag] = coverage_gaps(yearly_terms(2021, 2022, 2024, 2025, 2026), AS_OF, 5)
    assert "from 2023-01-01 to 2024-01-01 (365 days, between P-2022 and P-2024)" in flag.message


def test_gap_at_the_start_begins_where_the_checked_years_begin():
    [flag] = coverage_gaps(yearly_terms(2023, 2024, 2025, 2026), AS_OF, 5)
    assert "from 2021-10-02 to 2023-01-01 (456 days, before P-2023)" in flag.message


def test_gap_at_the_end_runs_to_the_as_of_date():
    [flag] = coverage_gaps(yearly_terms(2021, 2022, 2023, 2024, 2025), AS_OF, 5)
    assert "from 2026-01-01 to 2026-10-02 (274 days, after P-2025)" in flag.message


def test_gap_older_than_the_checked_years_is_ignored():
    assert coverage_gaps(yearly_terms(2021, 2022, 2024, 2025, 2026), AS_OF, 2) == []


def test_line_with_only_an_old_term_is_one_gap_over_all_the_years():
    [flag] = coverage_gaps([make_term("OLD", date(2015, 1, 1), date(2016, 1, 1))], AS_OF, 5)
    assert "from 2021-10-02 to 2026-10-02 (1826 days, no policy covers these years)" in flag.message


def test_overlapping_terms_have_no_gap():
    terms = [
        make_term("LONG", date(2020, 1, 1), date(2025, 6, 1)),
        make_term("INSIDE", date(2022, 1, 1), date(2023, 1, 1)),
        make_term("NOW", date(2025, 3, 1), date(2027, 3, 1)),
    ]
    assert coverage_gaps(terms, AS_OF, 5) == []


def test_gaps_are_found_per_line():
    terms = yearly_terms(2021, 2022, 2023, 2024, 2025, 2026)
    terms.append(make_term("W-1", date(2024, 1, 1), date(2027, 1, 1), line=WC))
    [flag] = coverage_gaps(terms, AS_OF, 5)
    assert flag.line_of_coverage == WC


def test_gaps_skip_lines_that_are_not_required():
    terms = [make_term("W-1", date(2024, 1, 1), date(2027, 1, 1), line=WC)]
    assert coverage_gaps(terms, AS_OF, 5, required=[GL]) == []


def test_incurred_equal_to_paid_plus_reserved_is_not_flagged():
    assert incurred_mismatches([make_claim(paid="100.00", reserved="50.00")]) == []


def test_incurred_mismatch_reports_the_difference():
    [flag] = incurred_mismatches([make_claim(paid="100.00", reserved="50.00", incurred="150.01")])
    assert "off by $0.01" in flag.message

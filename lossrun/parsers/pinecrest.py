"""Pinecrest Specialty: plain text with no table, two lines per claim.

    PSU-C-2025-0218 2025-09-03 OPEN PSU-PR-30981-25 Fire in grain storage room
    Paid 60,000.00 Outstanding 85,000.00 Total Incurred 145,000.00 Adj: R. Okafor

Policy terms are listed up front, each with a claim count.
"""

import re

import pdfplumber

from lossrun.models import LineOfCoverage, LossRun
from lossrun.parsers.base import ParseError, RunBuilder, check_equal, parse_date, search

NAME = "pinecrest"
MARKER = "PINECREST SPECIALTY"

DATE = "%Y-%m-%d"
DAY = r"\d{4}-\d{2}-\d{2}"
AMOUNT = r"([\d,.()-]+)"
TERM = re.compile(rf"^(\S+) ({DAY}) to ({DAY}) (\d+) claims?$")
CLAIM = re.compile(rf"^(\S+) ({DAY}) ([A-Z-]+) (\S+) .+$")
AMOUNTS = re.compile(rf"^Paid {AMOUNT} Outstanding {AMOUNT} Total Incurred {AMOUNT}")
TOTALS = re.compile(
    rf"^REPORT TOTALS Claims (\d+) Paid {AMOUNT} Outstanding {AMOUNT} Total Incurred {AMOUNT}"
)


def parse(pdf: pdfplumber.PDF, source_file: str) -> LossRun:
    pages = [page.extract_text() or "" for page in pdf.pages]
    first = pages[0]
    valuation = search(rf"valued as of ({DAY})", first, "valuation date").group(1)
    builder = RunBuilder(
        source_file=source_file,
        parser_name=NAME,
        carrier="Pinecrest Specialty Underwriters",
        insured_name=search(r"Named Insured:\s*(.+)", first, "named insured").group(1).strip(),
        line=LineOfCoverage.parse(search(r"Coverage:\s*(.+)", first, "line of coverage").group(1)),
        valuation_date=parse_date(valuation, DATE),
        page_count=len(pdf.pages),
    )
    expected_counts = {}
    totals_seen = False
    for page_no, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines()]
        for line, next_line in zip(lines, lines[1:] + [""]):
            if m := TERM.match(line):
                policy, start, end, count = m.groups()
                builder.term(policy, parse_date(start, DATE), parse_date(end, DATE), page_no)
                expected_counts[policy] = int(count)
            elif m := CLAIM.match(line):
                claim_no, loss_date, status, policy = m.groups()
                amounts = AMOUNTS.match(next_line)
                if amounts is None:
                    raise ParseError(f"page {page_no}: no amounts line after claim {claim_no}")
                paid, reserved, incurred = amounts.groups()
                builder.claim(
                    policy_number=policy,
                    claim_number=claim_no,
                    date_of_loss=parse_date(loss_date, DATE),
                    status=status,
                    paid=paid,
                    reserved=reserved,
                    incurred=incurred,
                    page=page_no,
                )
            elif m := TOTALS.match(line):
                count, paid, reserved, incurred = m.groups()
                builder.check_totals(
                    "report total",
                    builder.claims,
                    count=int(count),
                    paid=paid,
                    reserved=reserved,
                    incurred=incurred,
                )
                totals_seen = True
    if not totals_seen:
        raise ParseError("no report totals line")
    for policy, expected in expected_counts.items():
        check_equal(f"{policy} claim count", len(builder.claims_for(policy)), expected)
    return builder.build()

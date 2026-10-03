"""Harborline Casualty: one table per policy year, each ending in a subtotal.

A policy-year group can continue on the next page, so the current policy is
carried across pages.
"""

import re

import pdfplumber

from lossrun.models import LineOfCoverage, LossRun
from lossrun.parsers.base import (
    ParseError,
    RunBuilder,
    check_equal,
    parse_date,
    search,
    table_rows,
)

NAME = "harborline"
MARKER = "HARBORLINE CASUALTY"

HEADER = ["Claim No.", "Claimant", "Date of Injury", "Status", "Paid", "O/S Reserve", "Incurred"]
DATE = "%d-%b-%Y"
BANNER = re.compile(r"Policy Year (\S+) to (\S+)\s+Policy No\. (\S+)")
TOTAL = r"Grand Total \((\d+) claims?\) ([\d,.]+) ([\d,.]+) ([\d,.]+)"


def parse(pdf: pdfplumber.PDF, source_file: str) -> LossRun:
    pages = [page.extract_text() or "" for page in pdf.pages]
    first = pages[0]
    line = search(r"(.+) Loss Run by Policy Year", first, "line of coverage").group(1)
    valuation = search(r"Valuation Date:\s*(\S+)", first, "valuation date").group(1)
    builder = RunBuilder(
        source_file=source_file,
        parser_name=NAME,
        carrier="Harborline Casualty Group",
        insured_name=search(r"Insured:\s*(.+)", first, "insured").group(1).strip(),
        line=LineOfCoverage.parse(line),
        valuation_date=parse_date(valuation, DATE),
        page_count=len(pdf.pages),
    )
    policy = None
    subtotalled = set()
    for page_no, cells in table_rows(pdf):
        if banner := BANNER.match(cells[0]):
            start, end, policy = banner.groups()
            builder.term(policy, parse_date(start, DATE), parse_date(end, DATE), page_no)
        elif cells == HEADER or cells[0].startswith("No claims reported"):
            continue
        elif policy is None:
            raise ParseError(f"page {page_no}: row before any policy year: {cells}")
        elif cells[0].startswith("Subtotal"):
            count = search(r"\((\d+) claims?\)", cells[0], "subtotal count").group(1)
            builder.check_totals(
                f"{policy} subtotal",
                builder.claims_for(policy),
                count=int(count),
                paid=cells[4],
                reserved=cells[5],
                incurred=cells[6],
            )
            subtotalled.add(policy)
        elif len(cells) == len(HEADER):
            claim_no, _claimant, injury_date, status, paid, reserve, incurred = cells
            builder.claim(
                policy_number=policy,
                claim_number=claim_no,
                date_of_loss=parse_date(injury_date, DATE),
                status=status,
                paid=paid,
                reserved=reserve,
                incurred=incurred,
                page=page_no,
            )
        else:
            raise ParseError(f"page {page_no}: unexpected row {cells}")

    with_claims = {c.policy_number for c in builder.claims}
    check_equal("policy years with a subtotal", subtotalled, with_claims)
    count, paid, reserved, incurred = search(TOTAL, "\n".join(pages), "grand total").groups()
    builder.check_totals(
        "grand total",
        builder.claims,
        count=int(count),
        paid=paid,
        reserved=reserved,
        incurred=incurred,
    )
    return builder.build()

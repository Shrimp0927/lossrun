"""Northfield Mutual: one table, one row per claim, totals row at the end."""

import pdfplumber

from lossrun.models import LineOfCoverage, LossRun
from lossrun.parsers.base import ParseError, RunBuilder, parse_date, search, table_rows

NAME = "northfield"
MARKER = "NORTHFIELD MUTUAL"

HEADER = [
    "Policy Number",
    "Policy Period",
    "Claim Number",
    "Date of Loss",
    "Description",
    "Status",
    "Paid",
    "Reserve",
    "Total Incurred",
]
DATE = "%m/%d/%Y"


def parse(pdf: pdfplumber.PDF, source_file: str) -> LossRun:
    text = pdf.pages[0].extract_text() or ""
    line = search(r"Loss Run Report\s+\S\s+(.+)", text, "line of coverage").group(1)
    valuation = search(r"Valued as of:\s*(\S+)", text, "valuation date").group(1)
    builder = RunBuilder(
        source_file=source_file,
        parser_name=NAME,
        carrier="Northfield Mutual Insurance Company",
        insured_name=search(r"Named Insured:\s*(.+)", text, "named insured").group(1).strip(),
        line=LineOfCoverage.parse(line),
        valuation_date=parse_date(valuation, DATE),
        page_count=len(pdf.pages),
    )
    totals_seen = False
    for page_no, cells in table_rows(pdf):
        if cells == HEADER:
            continue
        if len(cells) != len(HEADER):
            raise ParseError(f"page {page_no}: unexpected row {cells}")
        policy, period, claim_no, loss_date, _desc, status, paid, reserve, incurred = cells
        if policy == "Report Totals":
            builder.check_totals(
                "report total",
                builder.claims,
                count=int(claim_no.split()[0]),
                paid=paid,
                reserved=reserve,
                incurred=incurred,
            )
            totals_seen = True
            continue
        start, _, end = period.partition(" - ")
        builder.term(policy, parse_date(start, DATE), parse_date(end, DATE), page_no)
        if claim_no == "No claims reported":
            continue
        builder.claim(
            policy_number=policy,
            claim_number=claim_no,
            date_of_loss=parse_date(loss_date, DATE),
            status=status,
            paid=paid,
            reserved=reserve,
            incurred=incurred,
            page=page_no,
        )
    if not totals_seen:
        raise ParseError("no report totals row")
    return builder.build()

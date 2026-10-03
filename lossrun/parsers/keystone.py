"""Keystone Claims Administrators: a letter, mostly sentences with one small table.

There are no printed totals, so the only checks are the table header and the
claim count the letter states in words.
"""

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

NAME = "keystone"
MARKER = "KEYSTONE CLAIMS ADMINISTRATORS"

HEADER = [
    "File No.",
    "Policy No.",
    "Policy Term",
    "Date of Loss",
    "Status",
    "Paid",
    "Reserve",
    "Incurred",
]
DATE = "%m/%d/%Y"
COUNT_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def parse(pdf: pdfplumber.PDF, source_file: str) -> LossRun:
    pages = [page.extract_text() or "" for page in pdf.pages]
    line, insured = search(r"Re: (.+) claim status \S (.+)", pages[0], "subject line").groups()
    # Sentences wrap across lines, so join everything into one line before searching.
    letter_text = " ".join(" ".join(pages).split())
    valuation = search(r"valued as of ([A-Z][a-z]+ \d{1,2}, \d{4})", letter_text, "valuation date")
    builder = RunBuilder(
        source_file=source_file,
        parser_name=NAME,
        carrier="Keystone Claims Administrators",
        insured_name=insured.strip(),
        line=LineOfCoverage.parse(line),
        valuation_date=parse_date(valuation.group(1), "%B %d, %Y"),
        page_count=len(pdf.pages),
    )
    header_seen = False
    for page_no, cells in table_rows(pdf):
        if cells == HEADER:
            header_seen = True
            continue
        if len(cells) != len(HEADER):
            raise ParseError(f"page {page_no}: unexpected row {cells}")
        file_no, policy, term, loss_date, status, paid, reserve, incurred = cells
        start, _, end = term.partition(" - ")
        builder.term(policy, parse_date(start, DATE), parse_date(end, DATE), page_no)
        builder.claim(
            policy_number=policy,
            claim_number=file_no,
            date_of_loss=parse_date(loss_date, DATE),
            status=status,
            paid=paid,
            reserved=reserve,
            incurred=incurred,
            page=page_no,
        )
    if not header_seen:
        raise ParseError("no claims table")
    stated = (
        search(r"records show (\w+) claims?", letter_text, "stated claim count").group(1).lower()
    )
    if stated not in COUNT_WORDS:
        raise ParseError(f"unreadable claim count: {stated!r}")
    check_equal("stated claim count", len(builder.claims), COUNT_WORDS.index(stated))
    return builder.build()

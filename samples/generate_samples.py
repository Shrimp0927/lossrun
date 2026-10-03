"""Generate four made-up loss-run PDFs, each with a different layout.

    uv run python samples/generate_samples.py [out_dir]

All carriers, insureds and claims are fictional. The data is defined once as
`LossRun` objects (`build_runs`), then drawn in each layout.

Problems put in on purpose, as seen on 2026-10-02:

  STALE_VALUATION         keystone letter is valued 2026-05-29 (126 days old)
  OPEN_RESERVE            open claims with reserves in every file
  DUPLICATE_CLAIM_NUMBER  NGL-24-00318 and NGL-24-00911 are in both the
                          Northfield run and the Keystone letter
  POSSIBLE_DUPLICATE      KCA-118204 (Keystone) matches NGL-25-00131
                          (Northfield) on date of loss, line and incurred
  MISSING_LINE            no auto report in the set
  COVERAGE_GAP            GL has no 2022 term
  INCURRED_MISMATCH       HWC240311: 18,450.00 + 6,500.00 != 25,950.00
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from lossrun.models import Claim, ClaimStatus, LineOfCoverage, LossRun, PolicyTerm

NORTHFIELD = "northfield_gl.pdf"
HARBORLINE = "harborline_wc.pdf"
PINECREST = "pinecrest_property.pdf"
KEYSTONE = "keystone_gl_letter.pdf"

# Text columns that are printed on the PDFs but not kept in the claims table.
DESCRIPTIONS = {
    "NGL-21-00872": "Slip and fall, taproom entrance",
    "NGL-23-00219": "Customer vehicle struck by keg dolly",
    "NGL-23-01544": "Alleged foreign object - record only",
    "NGL-24-00318": "Bottle failure, laceration injury",
    "NGL-24-00911": "Trip on patio decking",
    "NGL-25-00131": "Allergic reaction, labeling dispute",
    "NGL-25-00764": "Damaged vendor tent, summer event",
    "KCA-118204": "Allergic reaction, labeling dispute",
    "HWC210344": "D. Marsh",
    "HWC210519": "L. Ortega",
    "HWC220127": "P. Nwosu",
    "HWC220402": "T. Lindqvist",
    "HWC220688": "A. Rahimi",
    "HWC240093": "S. Calloway",
    "HWC240311": "J. Baptiste",
    "HWC240570": "M. Okonjo",
    "HWC250048": "R. Feldman",
    "HWC250266": "K. Yamada",
    "HWC250431": "E. Sorensen",
    "HWC250702": "C. Abara",
    "HWC260035": "V. Petrov",
    "PSU-C-2022-0457": "Frozen pipe burst, taproom ceiling",
    "PSU-C-2023-1102": "Hail damage to warehouse roof",
    "PSU-C-2025-0218": "Fire in grain storage room",
    "PSU-C-2026-0077": "Theft of copper fittings",
}


def _run(
    *,
    source_file: str,
    carrier: str,
    insured: str,
    line: LineOfCoverage,
    valuation: date,
    terms: list[tuple[str, date, date]],
    claims: list[tuple[str, str, date, str, str, str, str]],
) -> LossRun:
    """claims: (policy_number, claim_number, date_of_loss, status, paid, reserved, incurred)."""
    common = dict(
        carrier=carrier,
        insured_name=insured,
        line_of_coverage=line,
        valuation_date=valuation,
        source_file=source_file,
        source_page=1,  # not the real page: that depends on the layout
    )
    term_objs = [
        PolicyTerm(policy_number=num, policy_period_start=start, policy_period_end=end, **common)
        for num, start, end in terms
    ]
    by_number = {t.policy_number: t for t in term_objs}
    claim_objs = [
        Claim(
            policy_number=pol,
            policy_period_start=by_number[pol].policy_period_start,
            policy_period_end=by_number[pol].policy_period_end,
            claim_number=num,
            date_of_loss=loss_date,
            status=ClaimStatus(status),
            paid=Decimal(paid),
            reserved=Decimal(reserved),
            incurred=Decimal(incurred),
            **common,
        )
        for pol, num, loss_date, status, paid, reserved, incurred in claims
    ]
    return LossRun(
        source_file=source_file,
        carrier=carrier,
        insured_name=insured,
        valuation_date=valuation,
        method="parser",
        page_count=1,
        terms=term_objs,
        claims=claim_objs,
    )


def build_runs() -> dict[str, LossRun]:
    """The data behind every sample file, keyed by file name."""
    d = date
    gl = "NGL-204418-"
    northfield = _run(
        source_file=NORTHFIELD,
        carrier="Northfield Mutual Insurance Company",
        insured="Brightwater Brewing Company LLC",
        line=LineOfCoverage.GL,
        valuation=d(2026, 9, 18),
        # No 2022 term: the GL coverage gap.
        terms=[(f"{gl}{y}", d(2000 + y, 1, 1), d(2001 + y, 1, 1)) for y in (21, 23, 24, 25, 26)],
        claims=[
            (gl + "21", "NGL-21-00872", d(2021, 8, 14), "closed", "12400.00", "0.00", "12400.00"),
            (gl + "23", "NGL-23-00219", d(2023, 3, 2), "closed", "3150.00", "0.00", "3150.00"),
            (gl + "23", "NGL-23-01544", d(2023, 11, 20), "closed", "0.00", "0.00", "0.00"),
            (gl + "24", "NGL-24-00318", d(2024, 6, 7), "open", "28750.00", "46250.00", "75000.00"),
            (gl + "24", "NGL-24-00911", d(2024, 9, 28), "closed", "8920.50", "0.00", "8920.50"),
            (gl + "25", "NGL-25-00131", d(2025, 2, 15), "open", "5200.00", "19800.00", "25000.00"),
            (gl + "25", "NGL-25-00764", d(2025, 7, 4), "closed", "1875.25", "0.00", "1875.25"),
        ],
    )

    wc = "HWC-77120-"
    harborline = _run(
        source_file=HARBORLINE,
        carrier="Harborline Casualty Group",
        insured="BRIGHTWATER BREWING COMPANY LLC",
        line=LineOfCoverage.WC,
        valuation=d(2026, 9, 30),
        terms=[(f"{wc}{y}", d(2000 + y, 7, 1), d(2001 + y, 7, 1)) for y in range(21, 27)],
        claims=[
            (wc + "21", "HWC210344", d(2021, 9, 12), "closed", "4210.00", "0.00", "4210.00"),
            (wc + "21", "HWC210519", d(2022, 2, 3), "closed", "15875.40", "0.00", "15875.40"),
            (wc + "22", "HWC220127", d(2022, 8, 22), "closed", "950.00", "0.00", "950.00"),
            (wc + "22", "HWC220402", d(2023, 1, 17), "closed", "22340.75", "0.00", "22340.75"),
            (wc + "22", "HWC220688", d(2023, 5, 30), "closed", "0.00", "0.00", "0.00"),
            (wc + "24", "HWC240093", d(2024, 7, 19), "closed", "6480.00", "0.00", "6480.00"),
            # On purpose: incurred is 1,000.00 more than paid + reserve.
            (wc + "24", "HWC240311", d(2024, 12, 5), "open", "18450.00", "6500.00", "25950.00"),
            (wc + "24", "HWC240570", d(2025, 4, 11), "closed", "1220.00", "0.00", "1220.00"),
            (wc + "25", "HWC250048", d(2025, 7, 28), "open", "31600.00", "42400.00", "74000.00"),
            (wc + "25", "HWC250266", d(2025, 10, 9), "closed", "2115.60", "0.00", "2115.60"),
            (wc + "25", "HWC250431", d(2026, 1, 23), "open", "7900.00", "12100.00", "20000.00"),
            (wc + "25", "HWC250702", d(2026, 5, 14), "closed", "640.00", "0.00", "640.00"),
            (wc + "26", "HWC260035", d(2026, 8, 6), "open", "1150.00", "8850.00", "10000.00"),
        ],
    )

    pr = "PSU-PR-30981-"
    pinecrest = _run(
        source_file=PINECREST,
        carrier="Pinecrest Specialty Underwriters",
        insured="Brightwater Brewing Co.",
        line=LineOfCoverage.PROPERTY,
        valuation=d(2026, 9, 25),
        terms=[(f"{pr}{y}", d(2000 + y, 6, 1), d(2001 + y, 6, 1)) for y in range(21, 27)],
        claims=[
            (
                pr + "22",
                "PSU-C-2022-0457",
                d(2022, 12, 24),
                "closed",
                "41200.00",
                "0.00",
                "41200.00",
            ),
            (pr + "23", "PSU-C-2023-1102", d(2023, 8, 19), "closed", "9860.00", "0.00", "9860.00"),
            (
                pr + "25",
                "PSU-C-2025-0218",
                d(2025, 9, 3),
                "open",
                "60000.00",
                "85000.00",
                "145000.00",
            ),
            (pr + "25", "PSU-C-2026-0077", d(2026, 3, 11), "closed", "3400.00", "0.00", "3400.00"),
        ],
    )

    keystone = _run(
        source_file=KEYSTONE,
        carrier="Keystone Claims Administrators",
        insured="Brightwater Brewing Company LLC",
        line=LineOfCoverage.GL,
        valuation=d(2026, 5, 29),  # stale
        terms=[(f"{gl}{y}", d(2000 + y, 1, 1), d(2001 + y, 1, 1)) for y in (24, 25)],
        claims=[
            # Same claim number as Northfield, older (lower) figures.
            (gl + "24", "NGL-24-00318", d(2024, 6, 7), "open", "21300.00", "38700.00", "60000.00"),
            # Same claim number and same figures as Northfield.
            (gl + "24", "NGL-24-00911", d(2024, 9, 28), "closed", "8920.50", "0.00", "8920.50"),
            # Keystone's own file number for what Northfield calls NGL-25-00131.
            (gl + "25", "KCA-118204", d(2025, 2, 15), "open", "2500.00", "22500.00", "25000.00"),
        ],
    )
    return {r.source_file: r for r in (northfield, harborline, pinecrest, keystone)}


_styles = getSampleStyleSheet()
_BODY = ParagraphStyle("body", parent=_styles["Normal"], fontSize=10, leading=14)
_SMALL = ParagraphStyle(
    "small", parent=_styles["Normal"], fontSize=8, leading=10, textColor=colors.grey
)


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _total(claims: list[Claim], field: str) -> Decimal:
    return sum((getattr(c, field) for c in claims), Decimal("0.00"))


def _claims_for(run: LossRun, term: PolicyTerm) -> list[Claim]:
    return [c for c in run.claims if c.policy_number == term.policy_number]


# Layout 1: one table (Northfield Mutual, GL)


def render_northfield(run: LossRun, path: Path) -> None:
    date_format = "%m/%d/%Y"
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(letter),
        invariant=1,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title="Loss Run Report",
    )
    title = ParagraphStyle("t", parent=_styles["Title"], alignment=0, fontSize=16, spaceAfter=2)
    story = [
        Paragraph("NORTHFIELD MUTUAL INSURANCE COMPANY", title),
        Paragraph("Loss Run Report &mdash; General Liability", _styles["Heading3"]),
        Paragraph(f"Named Insured: {run.insured_name}", _BODY),
        Paragraph(f"Valued as of: {run.valuation_date.strftime(date_format)}", _BODY),
        Paragraph("Report run date: 09/21/2026", _BODY),
        Spacer(1, 12),
    ]
    rows = [
        [
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
    ]
    for term in run.terms:
        start = term.policy_period_start.strftime(date_format)
        end = term.policy_period_end.strftime(date_format)
        period = f"{start} - {end}"
        claims = _claims_for(run, term)
        if not claims:
            rows.append([term.policy_number, period, "No claims reported", "", "", "", "", "", ""])
        for c in claims:
            rows.append(
                [
                    c.policy_number,
                    period,
                    c.claim_number,
                    c.date_of_loss.strftime(date_format),
                    DESCRIPTIONS[c.claim_number],
                    c.status.value.capitalize(),
                    _money(c.paid),
                    _money(c.reserved),
                    _money(c.incurred),
                ]
            )
    rows.append(
        [
            "Report Totals",
            "",
            f"{len(run.claims)} claims",
            "",
            "",
            "",
            _money(_total(run.claims, "paid")),
            _money(_total(run.claims, "reserved")),
            _money(_total(run.claims, "incurred")),
        ]
    )
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8edf3")),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (6, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story += [
        table,
        Spacer(1, 14),
        Paragraph(
            "Reserves are estimates and subject to change. This report is provided for "
            "informational purposes and does not alter any policy terms.",
            _SMALL,
        ),
    ]
    doc.build(story)


# Layout 2: claims grouped by policy year with subtotals (Harborline, WC)


def render_harborline(run: LossRun, path: Path) -> None:
    date_format = "%d-%b-%Y"
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        invariant=1,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Workers' Compensation Loss Run",
    )
    story = [
        Paragraph("Harborline Casualty Group", _styles["Title"]),
        Paragraph("Workers' Compensation Loss Run by Policy Year", _styles["Heading2"]),
        Paragraph(f"<b>Insured:</b> {run.insured_name}", _BODY),
        Paragraph(f"<b>Valuation Date:</b> {run.valuation_date.strftime(date_format)}", _BODY),
        Paragraph("<b>Status codes:</b> O = Open, C = Closed", _BODY),
        Spacer(1, 10),
    ]
    widths = [
        1.1 * inch,
        1.35 * inch,
        1.1 * inch,
        0.6 * inch,
        0.95 * inch,
        0.95 * inch,
        0.95 * inch,
    ]
    header = [
        "Claim No.",
        "Claimant",
        "Date of Injury",
        "Status",
        "Paid",
        "O/S Reserve",
        "Incurred",
    ]
    for term in run.terms:
        claims = _claims_for(run, term)
        banner = (
            f"Policy Year {term.policy_period_start.strftime(date_format)} to "
            f"{term.policy_period_end.strftime(date_format)}   Policy No. {term.policy_number}"
        )
        rows = [[banner] + [""] * 6, header]
        for c in claims:
            rows.append(
                [
                    c.claim_number,
                    DESCRIPTIONS[c.claim_number],
                    c.date_of_loss.strftime(date_format),
                    "O" if c.status is ClaimStatus.OPEN else "C",
                    _money(c.paid),
                    _money(c.reserved),
                    _money(c.incurred),
                ]
            )
        style = [
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e6dc")),
            ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        if claims:
            rows.append(
                [
                    f"Subtotal ({len(claims)} claim{'s' if len(claims) != 1 else ''})",
                    "",
                    "",
                    "",
                    _money(_total(claims, "paid")),
                    _money(_total(claims, "reserved")),
                    _money(_total(claims, "incurred")),
                ]
            )
            style += [("SPAN", (0, -1), (3, -1)), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]
        else:
            rows.append(["No claims reported for this policy year"] + [""] * 6)
            style += [("SPAN", (0, -1), (-1, -1))]
        table = Table(rows, colWidths=widths, repeatRows=2)
        table.setStyle(TableStyle(style))
        story += [table, Spacer(1, 14)]

    grand = Table(
        [
            [
                f"Grand Total ({len(run.claims)} claims)",
                "",
                "",
                "",
                _money(_total(run.claims, "paid")),
                _money(_total(run.claims, "reserved")),
                _money(_total(run.claims, "incurred")),
            ]
        ],
        colWidths=widths,
    )
    grand.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (3, 0)),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.append(grand)

    def footer(canv, doc_):
        canv.setFont("Helvetica", 8)
        canv.drawRightString(letter[0] - 0.75 * inch, 0.45 * inch, f"Page {doc_.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


# Layout 3: two text lines per claim, no table (Pinecrest, property)


def render_pinecrest(run: LossRun, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=letter, invariant=1)
    c.setTitle("Claim Detail Loss Run")
    left, y = 0.7 * inch, letter[1] - 0.8 * inch

    def text(
        s: str, *, bold: bool = False, size: float = 9, dy: float = 13, x: float = left
    ) -> None:
        nonlocal y
        c.setFont("Courier-Bold" if bold else "Courier", size)
        c.drawString(x, y, s)
        y -= dy

    text("PINECREST SPECIALTY UNDERWRITERS", bold=True, size=13, dy=16)
    text("CLAIM DETAIL LOSS RUN", bold=True, size=10, dy=20)
    text(f"Named Insured:  {run.insured_name}")
    text("Coverage:       Commercial Property")
    text(f"Losses valued as of {run.valuation_date.isoformat()}", dy=22)

    text("POLICY TERMS INCLUDED", bold=True)
    for term in run.terms:
        n = len(_claims_for(run, term))
        text(
            f"  {term.policy_number}   {term.policy_period_start.isoformat()} to "
            f"{term.policy_period_end.isoformat()}   {n} claim{'s' if n != 1 else ''}"
        )
    y -= 10

    text("CLAIM DETAIL", bold=True)
    text(
        "Claim No.         Loss Date    Status   Policy            Cause of Loss", bold=True, dy=11
    )
    text("      Paid / Outstanding / Total Incurred / Adjuster", bold=True, dy=6)
    c.line(left, y + 2, letter[0] - left, y + 2)
    y -= 12
    adjusters = ["R. Okafor", "M. Delacroix", "R. Okafor", "H. Brandt"]
    for claim, adjuster in zip(run.claims, adjusters):
        text(
            f"{claim.claim_number}   {claim.date_of_loss.isoformat()}   "
            f"{claim.status.value.upper():<6}   {claim.policy_number}   "
            f"{DESCRIPTIONS[claim.claim_number]}",
            dy=12,
        )
        text(
            f"      Paid {_money(claim.paid)}   Outstanding {_money(claim.reserved)}   "
            f"Total Incurred {_money(claim.incurred)}   Adj: {adjuster}",
            dy=20,
        )
    c.line(left, y + 10, letter[0] - left, y + 10)
    text(
        f"REPORT TOTALS   Claims {len(run.claims)}   Paid {_money(_total(run.claims, 'paid'))}   "
        f"Outstanding {_money(_total(run.claims, 'reserved'))}   "
        f"Total Incurred {_money(_total(run.claims, 'incurred'))}",
        bold=True,
        size=8.5,
    )
    c.setFont("Courier", 8)
    c.drawString(left, 0.6 * inch, "Pinecrest Specialty Underwriters - Confidential - Page 1 of 1")
    c.save()


# Layout 4: mostly sentences with a small table (Keystone letter, GL)


def _short_date(value: date) -> str:
    return f"{value.month}/{value.day}/{value.year}"


def render_keystone(run: LossRun, path: Path) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        invariant=1,
        leftMargin=1.1 * inch,
        rightMargin=1.1 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title="Claims status letter",
    )
    head = ParagraphStyle(
        "head", parent=_styles["Normal"], fontName="Times-Bold", fontSize=15, leading=18
    )
    body = ParagraphStyle(
        "letter",
        parent=_styles["Normal"],
        fontName="Times-Roman",
        fontSize=11,
        leading=15,
        spaceAfter=10,
    )
    valuation = f"{run.valuation_date:%B} {run.valuation_date.day}, {run.valuation_date.year}"
    story = [
        Paragraph("Keystone Claims Administrators", head),
        Paragraph(
            "Third-Party Claims Administration | 400 Foundry Row, Suite 12 | Dayton, OH", _SMALL
        ),
        Spacer(1, 22),
        Paragraph("June 2, 2026", body),
        Paragraph(
            "Alder &amp; Finch Insurance Brokers<br/>Attn: Commercial Lines Service Team", body
        ),
        Paragraph(f"<b>Re: General Liability claim status &mdash; {run.insured_name}</b>", body),
        Paragraph("To whom it may concern:", body),
        Paragraph(
            "At your request we are providing the current status of the General Liability claims "
            "that Keystone Claims Administrators handles on behalf of Northfield Mutual Insurance "
            f"Company for the insured named above. All figures in this letter are valued as of "
            f"{valuation} and reflect payments and reserves posted through that date.",
            body,
        ),
        Paragraph(
            "Carrier claim numbers are shown where the carrier has assigned one; a claim still "
            "pending carrier set-up is shown under our own file number. Our records show three "
            "claims under the policy terms listed below.",
            body,
        ),
    ]
    rows = [
        [
            "File No.",
            "Policy No.",
            "Policy Term",
            "Date of Loss",
            "Status",
            "Paid",
            "Reserve",
            "Incurred",
        ]
    ]
    for c in run.claims:
        rows.append(
            [
                c.claim_number,
                c.policy_number,
                f"{_short_date(c.policy_period_start)} - {_short_date(c.policy_period_end)}",
                _short_date(c.date_of_loss),
                c.status.value.capitalize(),
                f"${_money(c.paid)}",
                f"${_money(c.reserved)}",
                f"${_money(c.incurred)}",
            ]
        )
    table = Table(rows)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story += [
        table,
        Spacer(1, 14),
        Paragraph(
            "The open bottle-failure matter remains in litigation and its reserve may be revised "
            "following the mediation scheduled for later this summer. We are not aware of any "
            "other reported incidents under these policies.",
            body,
        ),
        Paragraph(
            "This letter is a summary prepared for the broker of record and is not a "
            "carrier-issued loss run. Please contact our office with any questions.",
            body,
        ),
        Spacer(1, 10),
        Paragraph("Sincerely,<br/><br/>Dana Whitlock<br/>Senior Claims Examiner", body),
    ]
    doc.build(story)


RENDERERS = {
    NORTHFIELD: render_northfield,
    HARBORLINE: render_harborline,
    PINECREST: render_pinecrest,
    KEYSTONE: render_keystone,
}


def generate(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, run in build_runs().items():
        RENDERERS[name](run, out_dir / name)
        paths.append(out_dir / name)
    return paths


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    for p in generate(target):
        print(p)

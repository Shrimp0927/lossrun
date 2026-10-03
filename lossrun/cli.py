"""Command line entry point: lossrun process samples/*.pdf --out report.xlsx"""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import anthropic
import typer

from lossrun.combine import merge_claims, summarize
from lossrun.export import write_json, write_xlsx
from lossrun.extract import ExtractionError, extract_file
from lossrun.flags import build_flags
from lossrun.models import Flag, LineOfCoverage, LossRun, Report, SourceInfo

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main() -> None:
    """Combine insurance loss-run PDFs from different carriers into one claims table."""


def build_report(
    paths: list[Path],
    *,
    as_of: date,
    required_lines: list[LineOfCoverage] | None = None,
    years: int = 5,
    client: anthropic.Anthropic | None = None,
) -> Report:
    """Read each file, combine the claims, then flag problems."""
    runs: list[LossRun] = []
    sources: list[SourceInfo] = []
    for path in paths:
        try:
            run = extract_file(path, client)
        except (ExtractionError, OSError) as exc:
            sources.append(SourceInfo(source_file=path.name, method="failed", detail=str(exc)))
            continue
        runs.append(run)
        sources.append(
            SourceInfo(
                source_file=run.source_file,
                carrier=run.carrier,
                method=run.method,
                detail=run.method_detail,
                valuation_date=run.valuation_date,
                page_count=run.page_count,
                claim_count=len(run.claims),
            )
        )
    return Report(
        as_of=as_of,
        files=sources,
        claims=merge_claims(runs),
        summary=summarize(runs),
        flags=build_flags(runs, as_of=as_of, required_lines=required_lines, years=years),
    )


def parse_lines(text: str | None) -> list[LineOfCoverage]:
    if not text:
        return []
    try:
        return [LineOfCoverage.parse(part) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        valid = ", ".join(line.value for line in LineOfCoverage)
        raise typer.BadParameter(f"{exc}; expected a comma-separated list of: {valid}") from exc


def flag_reference(flag: Flag) -> str:
    """The most specific thing a flag points at, for the terminal listing."""
    if flag.claim_number:
        return flag.claim_number
    if flag.policy_number and "," not in flag.policy_number:
        return flag.policy_number
    return flag.source_file or (flag.line_of_coverage.value if flag.line_of_coverage else "-")


@app.command()
def process(
    files: Annotated[list[Path], typer.Argument(help="Loss-run PDFs to process.")],
    out: Annotated[Path | None, typer.Option("--out", help="Write an Excel workbook here.")] = None,
    json_out: Annotated[Path | None, typer.Option("--json", help="Write JSON here.")] = None,
    lines: Annotated[
        str | None,
        typer.Option("--lines", help="Required lines of coverage, e.g. GL,WC,auto,property."),
    ] = None,
    years: Annotated[
        int, typer.Option("--years", min=1, help="Years to check for coverage gaps.")
    ] = 5,
    as_of: Annotated[
        datetime | None,
        typer.Option("--as-of", formats=["%Y-%m-%d"], help="Report date. Defaults to today."),
    ] = None,
) -> None:
    """Read a set of loss runs, combine them and flag problems."""
    report = build_report(
        files,
        as_of=as_of.date() if as_of else date.today(),
        required_lines=parse_lines(lines),
        years=years,
    )

    for source in report.files:
        if source.method == "failed":
            message = f"FAILED  {source.source_file}: {source.detail}"
            typer.secho(message, fg=typer.colors.RED, err=True)
        else:
            detail = f" ({source.detail})" if source.detail else ""
            typer.echo(
                f"{source.method:<6}  {source.source_file}: {source.carrier}, "
                f"{source.claim_count} claims, valued {source.valuation_date}{detail}"
            )
    typer.echo(f"\n{len(report.claims)} claim rows, {len(report.summary)} policy terms")
    typer.echo(f"{len(report.flags)} flags")
    for flag in report.flags:
        typer.echo(f"  {flag.code.value:<22}  {flag_reference(flag):<22}  {flag.message}")

    if out:
        write_xlsx(report, out)
        typer.echo(f"\nwrote {out}")
    if json_out:
        write_json(report, json_out)
        typer.echo(f"wrote {json_out}")
    if any(source.method == "failed" for source in report.files):
        raise typer.Exit(code=1)

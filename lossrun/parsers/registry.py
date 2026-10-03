"""Which parser handles which carrier.

A parser is a module with NAME, MARKER (text from the top of page 1) and
parse(pdf, source_file). Files no parser matches are read by Claude instead.
"""

from types import ModuleType

from lossrun.parsers import harborline, keystone, northfield, pinecrest

PARSERS = [northfield, harborline, pinecrest, keystone]

# Only the top of the page is checked: further down, a report can mention
# other carriers (a claims handler's letter names the carrier it works for).
HEADER_LINES = 4


def detect_parser(first_page_text: str) -> ModuleType | None:
    header = "\n".join(first_page_text.splitlines()[:HEADER_LINES]).upper()
    return next((parser for parser in PARSERS if parser.MARKER in header), None)

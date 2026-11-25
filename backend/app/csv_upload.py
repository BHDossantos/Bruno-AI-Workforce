"""Read CSV uploads without writing records or invoking an import worker."""

import csv
import io

_HEADER_HINTS = ("first name", "last name", "name", "email", "e-mail", "company", "phone")


def csv_rows(content: str) -> list[dict]:
    """Validate row structure first; permit an export preamble and quoted line breaks."""
    lines = content.splitlines(keepends=True)
    start = 0
    for i, line in enumerate(lines[:10]):
        low = line.lower()
        if "," in line and any(hint in low for hint in _HEADER_HINTS):
            start = i
            break

    reader = csv.DictReader(io.StringIO("".join(lines[start:]), newline=""), strict=True)
    headings = [field.strip().casefold() for field in reader.fieldnames or [] if field.strip()]
    if len(set(headings)) != len(headings):
        raise csv.Error("CSV has duplicate column names. Rename duplicate columns and try again.")

    rows = []
    for row in reader:
        if None in row:
            raise csv.Error(f"CSV row ending on line {start + reader.line_num} has extra columns. Quote values that contain commas.")
        rows.append(row)
    return rows

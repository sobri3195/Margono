from collections import Counter
from csv import Error, reader
from io import StringIO
from typing import Literal

from pydantic import BaseModel, Field

from .errors import api_error


class CsvInput(BaseModel):
    content: str = Field(min_length=1, max_length=65_536)
    column: str = Field(default="Nama", min_length=1, max_length=128)


class ImportRow(BaseModel):
    row_number: int
    reference_label: str | None
    status: Literal["valid", "invalid"]
    duplicate: bool = False


class CsvPreview(BaseModel):
    columns: list[str]
    rows: list[ImportRow]


def preview_csv(payload: CsvInput) -> tuple[bytes, CsvPreview]:
    content = payload.content.encode("utf-8")
    if len(content) > 65_536 or "\x00" in payload.content:
        raise api_error(
            422, "invalid_csv", "CSV must be UTF-8 text and at most 64 KiB."
        )

    parser = reader(
        StringIO(payload.content.removeprefix("\ufeff"), newline=""), strict=True
    )
    try:
        columns = [value.strip() for value in next(parser, [])]
        if (
            not columns
            or len(columns) > 100
            or any(not item for item in columns)
            or len(columns) != len(set(columns))
            or payload.column not in columns
        ):
            raise api_error(
                422, "invalid_csv_columns", "Select a unique existing column."
            )
        column = columns.index(payload.column)
        rows = []
        for number, values in enumerate(parser, start=2):
            if number > 501:
                raise api_error(
                    422, "invalid_csv", "CSV must contain at most 500 data rows."
                )
            label = (
                values[column].strip() or None if len(values) == len(columns) else None
            )
            valid = label is not None and len(label) <= 500
            rows.append(
                ImportRow(
                    row_number=number,
                    reference_label=label if valid else None,
                    status="valid" if valid else "invalid",
                )
            )
    except Error:
        raise api_error(422, "invalid_csv", "CSV has malformed records.") from None

    if not rows:
        raise api_error(422, "invalid_csv", "CSV must contain at least one data row.")
    counts = Counter(
        row.reference_label.casefold()
        for row in rows
        if row.reference_label is not None
    )
    for row in rows:
        if row.reference_label is not None:
            row.duplicate = counts[row.reference_label.casefold()] > 1
    return content, CsvPreview(columns=columns, rows=rows)

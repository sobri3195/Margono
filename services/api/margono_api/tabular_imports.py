from base64 import b64decode
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from csv import Error as CsvError
from csv import reader
from io import BytesIO, StringIO
from typing import Literal
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field

from .errors import api_error

IMPORT_LIMIT = 65_536
SHEET_TAG = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class ImportContent(BaseModel):
    content: str = Field(min_length=1, max_length=87_384)
    format: Literal["csv", "xlsx", "manual"] = "csv"


class ImportInput(ImportContent):
    column: str = Field(default="Nama", min_length=1, max_length=128)


class ImportRow(BaseModel):
    row_number: int
    reference_label: str | None
    status: Literal["valid", "invalid"]
    duplicate: bool = False


class ImportColumns(BaseModel):
    columns: list[str]


class ImportPreview(ImportColumns):
    rows: list[ImportRow]


def original_bytes(payload: ImportContent) -> bytes:
    if payload.format == "xlsx":
        try:
            content = b64decode(payload.content, validate=True)
        except ValueError:
            raise api_error(
                422, "invalid_xlsx", "XLSX must use base64 encoding."
            ) from None
    else:
        content = payload.content.encode("utf-8")
        if "\x00" in payload.content:
            raise api_error(422, "invalid_csv", "CSV must be valid UTF-8 text.")
    if not 0 < len(content) <= IMPORT_LIMIT:
        raise api_error(422, "import_too_large", "Imports must be at most 64 KiB.")
    return content


def xlsx_rows(content: bytes) -> Iterator[list[str]]:
    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        if (
            len(entries) > 100
            or sum(entry.file_size for entry in entries) > 2_097_152
            or len({entry.filename for entry in entries}) != len(entries)
            or any(
                entry.flag_bits & 1
                or entry.filename.lower().endswith(".bin")
                or entry.filename.lower().startswith(
                    ("xl/externallinks/", "xl/embeddings/")
                )
                for entry in entries
            )
        ):
            raise api_error(
                422, "invalid_xlsx", "XLSX includes unsupported or oversized parts."
            )

        for entry in entries:
            if not entry.filename.endswith(".xml"):
                continue
            root = fromstring(archive.read(entry))
            if root.tag != SHEET_TAG + "worksheet":
                continue
            for row in root.iter(SHEET_TAG + "row"):
                if int(row.get("r", "1")) > 501:
                    raise api_error(
                        422, "too_many_rows", "XLSX must contain at most 500 data rows."
                    )
                if len(row) > 100:
                    raise api_error(
                        422, "invalid_xlsx", "XLSX must have at most 100 columns."
                    )
                for cell in row.iter(SHEET_TAG + "c"):
                    position = cell.get("r")
                    if position and coordinate_to_tuple(position)[1] > 100:
                        raise api_error(
                            422, "invalid_xlsx", "XLSX must have at most 100 columns."
                        )

    workbook = load_workbook(BytesIO(content), read_only=True, keep_links=False)
    try:
        if len(workbook.worksheets) != 1:
            raise api_error(422, "invalid_xlsx", "XLSX must have one worksheet.")
        sheet = workbook.worksheets[0]
        # Ignore the worksheet's approximate dimension hint and cap iteration.
        sheet.reset_dimensions()
        for cells in sheet.iter_rows(max_row=502, max_col=100):
            values = []
            last_used = 0
            for index, cell in enumerate(cells):
                if cell.value is not None:
                    last_used = index + 1
                # Formula cells are never evaluated or treated as labels.
                values.append(
                    cell.value
                    if cell.data_type == "s" and isinstance(cell.value, str)
                    else ""
                )
            yield values[:last_used]
    finally:
        workbook.close()


@contextmanager
def open_rows(payload: ImportContent, content: bytes) -> Iterator[Iterator[list[str]]]:
    if payload.format == "xlsx":
        rows = xlsx_rows(content)
        try:
            yield rows
        except (
            BadZipFile,
            DefusedXmlException,
            InvalidFileException,
            ParseError,
            KeyError,
            ValueError,
            TypeError,
            IndexError,
            OSError,
            RuntimeError,
        ):
            raise api_error(
                422, "invalid_xlsx", "XLSX contains malformed records."
            ) from None
        finally:
            rows.close()
    else:
        try:
            yield reader(StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        except CsvError:
            raise api_error(
                422, "invalid_csv", "CSV contains malformed records."
            ) from None


def read_columns(parser: Iterator[list[str]]) -> list[str]:
    columns = [value.strip() for value in next(parser, [])]
    if (
        not columns
        or len(columns) > 100
        or any(not item or len(item) > 128 or "\x00" in item for item in columns)
        or len(columns) != len(set(columns))
    ):
        raise api_error(
            422, "invalid_import_columns", "Import requires unique column names."
        )
    return columns


def preview_import_rows(payload: ImportInput, content: bytes) -> ImportPreview:
    with open_rows(payload, content) as parser:
        columns = read_columns(parser)
        if payload.column not in columns:
            raise api_error(422, "invalid_import_columns", "Select an existing column.")
        column = columns.index(payload.column)
        rows = []
        for number, values in enumerate(parser, start=2):
            if number > 501:
                raise api_error(
                    422, "too_many_rows", "Import must contain at most 500 data rows."
                )
            if payload.format == "xlsx":
                # XLSX serializes absent cells sparsely. Empty inner cells keep their position.
                values = values + [""] * (len(columns) - len(values))
            label = values[column].strip() if len(values) == len(columns) else ""
            valid = 0 < len(label) <= 500 and "\x00" not in label
            rows.append(
                ImportRow(
                    row_number=number,
                    reference_label=label if valid else None,
                    status="valid" if valid else "invalid",
                )
            )

    if not rows:
        raise api_error(
            422, "no_import_rows", "Import must contain at least one data row."
        )
    counts = Counter(
        row.reference_label.casefold()
        for row in rows
        if row.reference_label is not None
    )
    for row in rows:
        if row.reference_label is not None:
            row.duplicate = counts[row.reference_label.casefold()] > 1
    return ImportPreview(columns=columns, rows=rows)

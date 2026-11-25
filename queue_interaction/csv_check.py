import csv
from collections.abc import Iterator
from io import StringIO

from pydantic import BaseModel, ConfigDict, Field


class CsvFormatError(ValueError):
    pass


class CsvCheckResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: int
    duplicate_rows: int = Field(alias="duplicateRows")
    missing_by_column: dict[str, int] = Field(alias="missingByColumn")


def read_csv(text: str) -> tuple[list[str], Iterator[list[str]]]:
    reader = csv.reader(StringIO(text.removeprefix("\ufeff"), newline=""), strict=True)
    try:
        header_row = next((row for row in reader if row), [])
        headers = [cell.strip() for cell in header_row]
    except csv.Error as error:
        raise CsvFormatError(f"Invalid CSV header: {error}") from error

    if not headers or not all(headers) or len(set(headers)) != len(headers):
        raise CsvFormatError("CSV requires a header with unique, non-empty column names")

    def rows() -> Iterator[list[str]]:
        try:
            for row in reader:
                if not row:
                    continue
                if len(row) != len(headers):
                    raise CsvFormatError(f"CSV line {reader.line_num}: expected {len(headers)} fields")
                yield row
        except csv.Error as error:
            raise CsvFormatError(f"Invalid CSV near line {reader.line_num}: {error}") from error

    return headers, rows()


def check_csv(text: str) -> CsvCheckResult:
    headers, rows = read_csv(text)
    missing = dict.fromkeys(headers, 0)
    seen: set[tuple[str, ...]] = set()
    count = 0
    for row in rows:
        count += 1
        seen.add(tuple(row))
        for header, cell in zip(headers, row, strict=True):
            if not cell.strip():
                missing[header] += 1
    return CsvCheckResult(rows=count, duplicate_rows=count - len(seen), missing_by_column=missing)

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .csv_check import CsvCheckResult, read_csv

CsvText = Annotated[str, Field(min_length=1, max_length=65_536)]


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv: CsvText

    @field_validator("csv")
    @classmethod
    def validate_csv(cls, text: str) -> str:
        _, rows = read_csv(text)
        for _ in rows:
            pass
        return text


class CsvCheckRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    csv: CsvText


class JobCompleted(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    result: CsvCheckResult
    completed_at: AwareDatetime = Field(alias="completedAt")


class JobAccepted(BaseModel):
    id: UUID
    status: Literal["ACCEPTED"] = "ACCEPTED"


class JobDone(JobCompleted):
    status: Literal["DONE"] = "DONE"

from pydantic import BaseModel, ConfigDict


class Request(BaseModel):
    # A misspelt field is reported instead of silently falling back to its default.
    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    detail: str
    code: str

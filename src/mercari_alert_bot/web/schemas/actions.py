from typing import Final

from pydantic import BaseModel, Field

KEYWORD_DOCUMENT_MAX_LENGTH: Final = 100_000


class KeywordImportRequest(BaseModel):
    document_text: str = Field(max_length=KEYWORD_DOCUMENT_MAX_LENGTH)


class KeywordImportResponse(BaseModel):
    imported_rule_count: int
    skipped_rule_count: int

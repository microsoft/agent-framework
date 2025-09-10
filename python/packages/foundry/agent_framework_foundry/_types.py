from pydantic import BaseModel
from ._const import ReviewResult

class CriticAgentExecutorResponse(BaseModel):
    approved: ReviewResult
    feedback: str
    suggestions: str | None = None

class CriticAgentExecutorResponseRevision(CriticAgentExecutorResponse):
    revision: int

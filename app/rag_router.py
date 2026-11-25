"""
POST /ask : answer a question from FleetPilot's documents (RAG), with sources.
"""

from functools import lru_cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.db import get_conn
from app.llm.gateway import AllProvidersFailed, BudgetExceeded, LLMGateway
from app.llm.router import get_gateway
from rag.answer import answer_question
from rag.embeddings import OllamaEmbedder

router = APIRouter(tags=["RAG"])


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10)


class Source(BaseModel):
    n: int
    doc_id: str
    title: str
    source: str
    url: Optional[str]
    similarity: float


class AskResponse(BaseModel):
    answer: str
    answered_from_sources: bool       # False = "I don't know" or no valid citation
    cited: List[int]                  # source numbers used in the answer
    sources: List[Source]             # everything the LLM was shown
    provider: Optional[str]
    model: Optional[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    retrieval_ms: int
    llm_ms: int


@lru_cache(maxsize=1)
def get_embedder():
    return OllamaEmbedder()


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest, conn=Depends(get_conn), embedder=Depends(get_embedder),
        gateway: LLMGateway = Depends(get_gateway)):
    try:
        r = answer_question(request.question, embedder, conn, gateway, top_k=request.top_k,
                            min_similarity=config.RAG_MIN_SIMILARITY)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except AllProvidersFailed as exc:
        raise HTTPException(status_code=503, detail=f"All LLM providers failed: {exc}")
    return AskResponse(answer=r.answer, answered_from_sources=r.answered_from_sources, cited=r.cited,
                       sources=r.sources, provider=r.provider, model=r.model,
                       input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                       cost_usd=round(r.cost_usd, 6), retrieval_ms=r.retrieval_ms, llm_ms=r.llm_ms)

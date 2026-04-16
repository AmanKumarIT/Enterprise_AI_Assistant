"""
Chat API endpoint.
Exposes the RAG pipeline and LangGraph agent to the frontend.
"""
import logging
import uuid
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import time

from app.auth.deps import get_current_active_user, get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, CitationResponse
from app.services.embedding import get_embedder
from app.services.llm import LLMService
from app.retrieval.bm25 import BM25Index
from app.retrieval.rag_pipeline import RAGPipeline
from app.agents.query_agent import QueryRoutingAgent
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_bm25_index = BM25Index()
_embedder = None
_llm_service = None
_rag_pipeline = None
_agent = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from app.services.embedding import get_active_embedder
        _embedder = get_active_embedder()
    return _embedder


def _get_llm_service():
    global _llm_service
    if _llm_service is None:
        # Prefer Groq settings as requested, fallback to OpenAI if needed
        api_key = getattr(settings, "GROQ_API_KEY", "") or getattr(settings, "OPENAI_API_KEY", "")
        base_url = getattr(settings, "LLM_BASE_URL", None)
        model = getattr(settings, "LLM_MODEL", "llama3-70b-8192")

        logger.info("Using API Key Prefix: %s", api_key[:10] if api_key else "NONE")
        logger.info("Using Base URL: %s", base_url)
        logger.info("Using Model: %s", model)
        
        _llm_service = LLMService(
            api_key=api_key,
            model=model,
            base_url=base_url,
        )
    return _llm_service


def _get_rag_pipeline():
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline(
            embedder=_get_embedder(),
            llm_service=_get_llm_service(),
            bm25_index=_bm25_index,
            use_cross_encoder=False,
            dense_weight=0.7,
            sparse_weight=0.3,
        )
    return _rag_pipeline


def _get_agent():
    global _agent
    if _agent is None:
        _agent = QueryRoutingAgent(
            rag_pipeline=_get_rag_pipeline(),
            llm_service=_get_llm_service(),
            max_hops=3,
        )
    return _agent


@router.post("/query", response_model=ChatResponse)
async def chat_query(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ChatResponse:
    """
    Process a user query through the RAG pipeline or LangGraph agent.
    Returns a grounded answer with citations and confidence score.
    """
    try:
        if request.use_agent:
            agent = _get_agent()
            result = agent.run(
                query=request.query,
                workspace_id=request.workspace_id,
            )

            citations = [
                CitationResponse(**c) for c in result.get("citations", [])
            ]

            return ChatResponse(
                answer=result["answer"],
                citations=citations,
                confidence_score=result.get("confidence", 0.0),
                query_intent=result.get("query_intent", ""),
                target_sources=result.get("target_sources", []),
                retrieval_metadata={"hop_count": result.get("hop_count", 1)},
                session_id=request.session_id,
            )
        else:
            pipeline = _get_rag_pipeline()
            result = pipeline.execute(
                query=request.query,
                workspace_id=request.workspace_id,
                source_type_filter=request.source_type_filter,
                data_source_id=str(request.data_source_id) if request.data_source_id else None,
            )

            citations = [
                CitationResponse(
                    source_index=c.source_index,
                    source_type=c.source_type,
                    document_title=c.document_title,
                    source_uri=c.source_uri,
                    chunk_index=c.chunk_index,
                    retrieval_score=c.retrieval_score,
                    rerank_score=c.rerank_score,
                )
                for c in result.citations
            ]

            return ChatResponse(
                answer=result.answer,
                citations=citations,
                confidence_score=result.confidence_score,
                query_intent=result.query_intent,
                target_sources=result.target_sources,
                retrieval_metadata=result.retrieval_metadata,
                processing_time_ms=result.processing_time_ms,
                session_id=request.session_id,
            )

    except Exception as e:
        logger.error("Chat query failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/query/stream")
async def chat_query_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Stream the RAG response token-by-token via Server-Sent Events.
    """
    import json

    async def event_generator():
        try:
            overall_start = time.perf_counter()
            pipeline = _get_rag_pipeline()

            t = time.perf_counter()
            classification = pipeline.classifier.classify(request.query)
            logger.info(
                "TIMING | Classification: %.2f ms",
                (time.perf_counter() - t) * 1000
            )            
            yield f"data: {json.dumps({'type': 'classification', 'data': {'intent': classification['intent'].value, 'sources': classification['target_sources']}})}\n\n"

            t = time.perf_counter()
            results = pipeline.retriever.retrieve(
                query=request.query,
                workspace_id=request.workspace_id,
                top_k=20,
                source_type=request.source_type_filter,
            )
            logger.info(
                "TIMING | Retrieval: %.2f ms | Results=%d",
                (time.perf_counter() - t) * 1000,
                len(results)
            )

            yield f"data: {json.dumps({'type': 'retrieval', 'data': {'count': len(results)}})}\n\n"

            t = time.perf_counter()
            reranked = pipeline.reranker.rerank(
                query=request.query,
                results=results,
                top_k=10
            )
            logger.info(
                "TIMING | Rerank: %.2f ms",
                (time.perf_counter() - t) * 1000
            )

            t = time.perf_counter()
            compressed = pipeline.compressor.compress(reranked)
            context_text = pipeline.compressor.format_context(compressed)
            logger.info(
                "TIMING | Compression: %.2f ms | Context chars=%d",
                (time.perf_counter() - t) * 1000,
                len(context_text)
            )

            from app.services.llm import build_rag_messages
            messages = build_rag_messages(query=request.query, context=context_text)

            llm = _get_llm_service()
            full_answer = ""

            llm_start = time.perf_counter()
            first_token_logged = False

            async for token in llm.astream(messages):
                if not first_token_logged:
                    logger.info(
                        "TIMING | LLM First Token: %.2f ms",
                        (time.perf_counter() - llm_start) * 1000
                    )
                    first_token_logged = True

                full_answer += token
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

            logger.info(
                "TIMING | LLM Total Stream: %.2f ms",
                (time.perf_counter() - llm_start) * 1000
            )

            citations = []
            for i, r in enumerate(compressed, 1):
                p = r.get("payload", {})
                citations.append({
                    "source_index": i,
                    "source_type": p.get("source_type", ""),
                    "document_title": p.get("document_title", ""),
                    "source_uri": p.get("source_uri", ""),
                })

            logger.info(
                "TIMING | Total Chat Pipeline: %.2f ms",
                (time.perf_counter() - overall_start) * 1000
            )

            yield f"data: {json.dumps({'type': 'done', 'data': {'citations': citations}})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

"""
LangGraph-based multi-source query routing agent.
Routes queries to specialized tool nodes (SQL, Document, GitHub,
Slack, Jira) and supports multi-hop cross-source reasoning.
"""
import logging
import uuid
from typing import TypedDict, Annotated, Sequence, List, Dict, Any, Optional
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """State passed through the LangGraph agent."""
    query: str
    workspace_id: str
    messages: Annotated[Sequence[BaseMessage], "chat_messages"]
    classification: Dict[str, Any]
    retrieval_results: List[Dict[str, Any]]
    source_results: Dict[str, List[Dict[str, Any]]]
    final_answer: str
    citations: List[Dict[str, Any]]
    confidence: float
    current_step: str
    hop_count: int
    max_hops: int
    needs_more_info: bool


ROUTER_SYSTEM_PROMPT = """You are a query routing agent for an enterprise knowledge system.
Given a user query and initial classification, decide which data sources to search.

Available sources: DOCUMENTS, GITHUB, SQL_DATABASE, SLACK, CONFLUENCE, NOTION, JIRA

Respond with a JSON object:
{{
    "sources": ["SOURCE1", "SOURCE2"],
    "reasoning": "brief explanation",
    "needs_decomposition": false,
    "sub_queries": []
}}

If the query is complex and needs breaking down, set needs_decomposition=true
and provide sub_queries, each with a target source."""


SYNTHESIS_SYSTEM_PROMPT = """You are an Enterprise Knowledge Assistant synthesizing information from multiple enterprise data sources.

RULES:
1. Synthesize information from ALL provided source results
2. Use [Source: TYPE - TITLE] citation format
3. If sources conflict, note the discrepancy
4. Be precise and professional
5. Never fabricate information not in the provided results

Provide a comprehensive answer with inline citations."""


class QueryRoutingAgent:
    """
    LangGraph agent that routes queries across multiple data sources,
    supports multi-hop retrieval, and synthesizes cross-source answers.
    """

    def __init__(
        self,
        rag_pipeline,
        llm_service,
        max_hops: int = 3,
    ):
        self.rag_pipeline = rag_pipeline
        self.llm_service = llm_service
        self.max_hops = max_hops
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(AgentState)

        workflow.add_node("classify", self._classify_node)
        workflow.add_node("route", self._route_node)
        workflow.add_node("retrieve_documents", self._retrieve_documents_node)
        workflow.add_node("retrieve_code", self._retrieve_code_node)
        workflow.add_node("retrieve_sql", self._retrieve_sql_node)
        workflow.add_node("retrieve_slack", self._retrieve_slack_node)
        workflow.add_node("retrieve_jira", self._retrieve_jira_node)
        workflow.add_node("retrieve_confluence", self._retrieve_confluence_node)
        workflow.add_node("synthesize", self._synthesize_node)
        workflow.add_node("evaluate", self._evaluate_node)

        workflow.set_entry_point("classify")
        workflow.add_edge("classify", "route")

        workflow.add_conditional_edges(
            "route",
            self._route_decision,
            {
                "documents": "retrieve_documents",
                "code": "retrieve_code",
                "sql": "retrieve_sql",
                "slack": "retrieve_slack",
                "jira": "retrieve_jira",
                "confluence": "retrieve_confluence",
                "synthesize": "synthesize",
            },
        )

        for node in [
            "retrieve_documents", "retrieve_code", "retrieve_sql",
            "retrieve_slack", "retrieve_jira", "retrieve_confluence",
        ]:
            workflow.add_edge(node, "synthesize")

        workflow.add_edge("synthesize", "evaluate")

        workflow.add_conditional_edges(
            "evaluate",
            self._evaluate_decision,
            {
                "done": END,
                "retry": "route",
            },
        )

        return workflow.compile()

    def run(self, query: str, workspace_id: uuid.UUID) -> Dict[str, Any]:
        """Execute the agent graph."""
        initial_state: AgentState = {
            "query": query,
            "workspace_id": str(workspace_id),
            "messages": [HumanMessage(content=query)],
            "classification": {},
            "retrieval_results": [],
            "source_results": {},
            "final_answer": "",
            "citations": [],
            "confidence": 0.0,
            "current_step": "classify",
            "hop_count": 0,
            "max_hops": self.max_hops,
            "needs_more_info": False,
        }

        result = self.graph.invoke(initial_state, {"recursion_limit": 50})

        return {
            "answer": result["final_answer"],
            "citations": result["citations"],
            "confidence": result["confidence"],
            "query_intent": result["classification"].get("intent", ""),
            "target_sources": result["classification"].get("target_sources", []),
            "hop_count": result["hop_count"],
        }

    def _route_node(self, state: AgentState) -> AgentState:
        """Passive node for routing decisions."""
        return state

    def _classify_node(self, state: AgentState) -> AgentState:
        """Classify the query intent and determine target sources."""
        classification = self.rag_pipeline.classifier.classify(state["query"])
        state["classification"] = {
            "intent": classification["intent"].value,
            "target_sources": classification["target_sources"],
            "confidence": classification["confidence"],
            "reasoning": classification["reasoning"],
        }
        logger.info("Agent classified query: %s", state["classification"])
        return state

    def _route_decision(self, state: AgentState) -> str:
        """Determine which retrieval node to route to."""
        sources = state["classification"].get("target_sources", [])
        already_searched = set(state["source_results"].keys())

        for source in sources:
            if source in already_searched:
                continue

            # Map source types to specialized nodes
            if source in ("PDF", "DOCX", "TXT"):
                return "documents"
            elif source == "GITHUB":
                return "code"
            elif source == "SQL_DATABASE":
                return "sql"
            elif source == "SLACK":
                return "slack"
            elif source == "JIRA":
                return "jira"
            elif source in ("CONFLUENCE", "NOTION"):
                return "confluence"

        # If all target sources are already searched, we must synthesize
        return "synthesize"

    def _retrieve_documents_node(self, state: AgentState) -> AgentState:
        """Retrieve from document sources (PDF/DOCX/TXT)."""
        results = self._do_retrieval(state, source_types=["PDF", "DOCX", "TXT"])
        for st in ["PDF", "DOCX", "TXT"]:
            state["source_results"][st] = results
        state["retrieval_results"].extend(results)
        return state

    def _retrieve_code_node(self, state: AgentState) -> AgentState:
        """Retrieve from GitHub sources."""
        results = self._do_retrieval(state, source_types=["GITHUB"])
        state["source_results"]["GITHUB"] = results
        state["retrieval_results"].extend(results)
        return state

    def _retrieve_sql_node(self, state: AgentState) -> AgentState:
        """Retrieve from SQL database sources."""
        results = self._do_retrieval(state, source_types=["SQL_DATABASE"])
        state["source_results"]["SQL_DATABASE"] = results
        state["retrieval_results"].extend(results)
        return state

    def _retrieve_slack_node(self, state: AgentState) -> AgentState:
        """Retrieve from Slack sources."""
        results = self._do_retrieval(state, source_types=["SLACK"])
        state["source_results"]["SLACK"] = results
        state["retrieval_results"].extend(results)
        return state

    def _retrieve_jira_node(self, state: AgentState) -> AgentState:
        """Retrieve from Jira sources."""
        results = self._do_retrieval(state, source_types=["JIRA"])
        state["source_results"]["JIRA"] = results
        state["retrieval_results"].extend(results)
        return state

    def _retrieve_confluence_node(self, state: AgentState) -> AgentState:
        """Retrieve from Confluence/Notion sources."""
        results_c = self._do_retrieval(state, source_types=["CONFLUENCE"])
        results_n = self._do_retrieval(state, source_types=["NOTION"])
        combined = results_c + results_n
        state["source_results"]["CONFLUENCE"] = results_c
        state["source_results"]["NOTION"] = results_n
        state["retrieval_results"].extend(combined)
        return state

    def _do_retrieval(
        self, state: AgentState, source_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Execute retrieval for specific source types."""
        all_results = []
        workspace_id = uuid.UUID(state["workspace_id"])

        for source_type in source_types:
            try:
                results = self.rag_pipeline.retriever.retrieve(
                    query=state["query"],
                    workspace_id=workspace_id,
                    top_k=10,
                    source_type=source_type,
                )
                all_results.extend(results)
            except Exception as e:
                logger.error("Retrieval failed for %s: %s", source_type, str(e))

        return all_results

    def _synthesize_node(self, state: AgentState) -> AgentState:
        """Synthesize a final answer from all retrieved results."""
        all_results = state["retrieval_results"]

        if not all_results:
            state["final_answer"] = (
                "I couldn't find relevant information across the enterprise data sources. "
                "Please ensure the relevant sources have been connected and ingested."
            )
            state["confidence"] = 0.0
            return state

        reranked = self.rag_pipeline.reranker.rerank(
            query=state["query"],
            results=all_results,
            top_k=self.rag_pipeline.max_reranked_results,
        )

        compressed = self.rag_pipeline.compressor.compress(reranked, query=state["query"])
        context_text = self.rag_pipeline.compressor.format_context(compressed)

        from app.services.llm import LLMMessage

        messages = [
            LLMMessage(role="system", content=SYNTHESIS_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=f"Context from enterprise sources:\n\n{context_text}\n\n---\n\nQuestion: {state['query']}\n\nProvide a comprehensive answer with citations.",
            ),
        ]

        answer = self.llm_service.generate(messages)
        state["final_answer"] = answer

        citations = []
        for i, result in enumerate(compressed, 1):
            payload = result.get("payload", {})
            citations.append({
                "source_index": i,
                "source_type": payload.get("source_type", "Unknown"),
                "document_title": payload.get("document_title", "Untitled"),
                "source_uri": payload.get("source_uri", ""),
                "retrieval_score": result.get("hybrid_score", result.get("score", 0.0)),
                "rerank_score": result.get("rerank_score", 0.0),
            })
        state["citations"] = citations

        state["confidence"] = self.rag_pipeline._compute_confidence(
            classification=state["classification"],
            results=compressed,
            answer=answer,
        )

        return state

    def _evaluate_node(self, state: AgentState) -> AgentState:
        """Evaluate whether the answer is satisfactory or needs more hops."""
        state["hop_count"] += 1

        # Only consider retrying if we are under the hop limit and confidence is low
        if state["confidence"] < 0.4 and state["hop_count"] < state["max_hops"]:
            # Check if there are ANY unsearched sources left in the system
            all_possible_sources = ["PDF", "DOCX", "TXT", "GITHUB", "SQL_DATABASE", "SLACK", "JIRA", "CONFLUENCE", "NOTION"]
            unsearched = [s for s in all_possible_sources if s not in state["source_results"]]
            
            if unsearched:
                state["needs_more_info"] = True
                state["classification"]["target_sources"] = unsearched
                logger.info(
                    "Low confidence (%.2f), retrying. Hop: %d/%d. New targets: %s",
                    state["confidence"],
                    state["hop_count"],
                    state["max_hops"],
                    unsearched,
                )
            else:
                # No more sources to search, we must stop here
                state["needs_more_info"] = False
                logger.info("Low confidence but all sources already searched. Finalizing.")
        else:
            state["needs_more_info"] = False
            if state["hop_count"] >= state["max_hops"]:
                logger.info("Reached max hops (%d), finalizing answer.", state["max_hops"])

        return state

    def _evaluate_decision(self, state: AgentState) -> str:
        """Decide whether to continue or finish."""
        if state["needs_more_info"] and state["hop_count"] < state["max_hops"]:
            return "retry"
        return "done"

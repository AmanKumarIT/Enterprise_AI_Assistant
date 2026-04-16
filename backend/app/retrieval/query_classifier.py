"""
Query classifier for intent detection and source routing.
Determines which data sources to query based on the user's question.
"""
import logging
import re
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    DOCUMENT_SEARCH = "document_search"
    CODE_SEARCH = "code_search"
    SQL_QUERY = "sql_query"
    SLACK_SEARCH = "slack_search"
    JIRA_SEARCH = "jira_search"
    CONFLUENCE_SEARCH = "confluence_search"
    MULTI_SOURCE = "multi_source"
    GENERAL = "general"


SOURCE_KEYWORDS: Dict[QueryIntent, List[str]] = {
    QueryIntent.CODE_SEARCH: [
        "code", "function", "class", "method", "api", "endpoint", "implementation",
        "repository", "repo", "github", "git", "commit", "branch", "module",
        "import", "library", "package", "debugging", "bug fix", "refactor",
        "authentication flow", "backend repo", "frontend code", "codebase",
    ],
    QueryIntent.SQL_QUERY: [
        "database", "table", "query", "sql", "schema", "column", "row",
        "select", "insert", "join", "aggregate", "count", "sum",
        "sales data", "revenue", "customer data", "orders", "transactions",
        "report", "analytics data", "metrics", "statistics",
    ],
    QueryIntent.SLACK_SEARCH: [
        "slack", "channel", "message", "discussion", "conversation",
        "said", "mentioned", "talked about", "discussed", "thread",
        "team chat", "engineering discussed", "what did", "who said",
    ],
    QueryIntent.JIRA_SEARCH: [
        "jira", "ticket", "issue", "bug", "sprint", "story", "epic",
        "task", "assignee", "status", "priority", "backlog", "blocker",
        "checkout failure", "regression", "defect", "feature request",
    ],
    QueryIntent.CONFLUENCE_SEARCH: [
        "confluence", "wiki", "documentation", "doc", "page", "knowledge base",
        "notion", "guide", "runbook", "playbook", "how to", "process",
        "procedure", "onboarding", "architecture doc",
    ],
    QueryIntent.DOCUMENT_SEARCH: [
        "document", "pdf", "file", "report", "summary", "summarize",
        "presentation", "slide", "whitepaper", "manual", "handbook",
        "q1", "q2", "q3", "q4", "quarterly", "annual",
    ],
}

MULTI_SOURCE_INDICATORS = [
    "compare", "cross-reference", "correlate", "relate",
    "combine", "from slack and jira", "across", "between",
    "from all sources", "everywhere",
]


class QueryClassifier:
    """
    Classifies user queries to determine intent and
    which data sources should be queried.
    Supports both rule-based classification and optional LLM-based
    classification for ambiguous queries.
    """

    def __init__(self, llm_service=None):
        self._llm = llm_service

    def classify(self, query: str) -> Dict[str, Any]:
        """
        Classify a query and return intent, target sources, and confidence.

        Returns:
            {
                "intent": QueryIntent,
                "target_sources": List[str],
                "confidence": float,
                "reasoning": str,
            }
        """
        query_lower = query.lower().strip()

        if self._is_multi_source(query_lower):
            sources = self._detect_all_relevant_sources(query_lower)
            return {
                "intent": QueryIntent.MULTI_SOURCE,
                "target_sources": sources if len(sources) > 1 else self._all_sources(),
                "confidence": 0.8,
                "reasoning": "Query requires cross-source reasoning",
            }

        scores: Dict[QueryIntent, float] = {}
        for intent, keywords in SOURCE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            weighted = score / len(keywords) if keywords else 0.0
            if score > 0:
                scores[intent] = weighted

        if not scores:
            return {
                "intent": QueryIntent.GENERAL,
                "target_sources": self._all_sources(),
                "confidence": 0.3,
                "reasoning": "No strong source signal detected; searching all sources",
            }

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        close_intents = [
            intent for intent, score in scores.items()
            if score >= best_score * 0.7 and intent != best_intent
        ]

        if close_intents:
            all_intents = [best_intent] + close_intents
            sources = []
            for intent in all_intents:
                sources.extend(self._intent_to_sources(intent))
            return {
                "intent": QueryIntent.MULTI_SOURCE,
                "target_sources": list(set(sources)),
                "confidence": min(best_score + 0.2, 0.9),
                "reasoning": f"Multiple relevant sources detected: {[i.value for i in all_intents]}",
            }

        return {
            "intent": best_intent,
            "target_sources": self._intent_to_sources(best_intent),
            "confidence": min(best_score + 0.3, 0.95),
            "reasoning": f"Query matched {best_intent.value} intent",
        }

    def _is_multi_source(self, query: str) -> bool:
        return any(indicator in query for indicator in MULTI_SOURCE_INDICATORS)

    def _detect_all_relevant_sources(self, query: str) -> List[str]:
        sources = []
        for intent, keywords in SOURCE_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                sources.extend(self._intent_to_sources(intent))
        return list(set(sources)) if sources else self._all_sources()

    def _intent_to_sources(self, intent: QueryIntent) -> List[str]:
        mapping = {
            QueryIntent.DOCUMENT_SEARCH: ["PDF", "DOCX", "TXT"],
            QueryIntent.CODE_SEARCH: ["GITHUB"],
            QueryIntent.SQL_QUERY: ["SQL_DATABASE"],
            QueryIntent.SLACK_SEARCH: ["SLACK"],
            QueryIntent.JIRA_SEARCH: ["JIRA"],
            QueryIntent.CONFLUENCE_SEARCH: ["CONFLUENCE", "NOTION"],
            QueryIntent.GENERAL: self._all_sources(),
            QueryIntent.MULTI_SOURCE: self._all_sources(),
        }
        return mapping.get(intent, self._all_sources())

    def _all_sources(self) -> List[str]:
        return ["PDF", "DOCX", "TXT", "GITHUB", "SQL_DATABASE", "SLACK", "CONFLUENCE", "NOTION", "JIRA"]

"""
LLM service abstraction.
Provides a unified interface for calling LLMs (OpenAI, local, etc.)
with structured output, streaming support, and retry logic.
"""
import logging
import json
from typing import List, Dict, Any, Optional, AsyncGenerator

logger = logging.getLogger(__name__)


class LLMMessage:
    """Represents a single message in a conversation."""

    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class LLMService:
    """
    Abstracted LLM service supporting OpenAI-compatible APIs.
    Handles prompt construction, retries, and response parsing.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ):
        import openai

        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = openai.OpenAI(**client_kwargs)
        self._async_client = openai.AsyncOpenAI(**client_kwargs)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        logger.info("LLM service initialized: model=%s", model)

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Synchronous generation."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        return response.choices[0].message.content or ""

    async def agenerate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Asynchronous generation."""
        response = await self._async_client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        return response.choices[0].message.content or ""

    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Async streaming generation."""
        stream = await self._async_client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_format: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate with JSON structured output."""
        messages_with_format = messages.copy()
        messages_with_format.append(
            LLMMessage(
                role="system",
                content="Respond ONLY with valid JSON matching the requested format.",
            )
        )

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages_with_format],
            temperature=0.0,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Failed to parse structured LLM response: %s", content[:200])
            return {"error": "Failed to parse response", "raw": content}


RAG_SYSTEM_PROMPT = """You are an Enterprise Knowledge Assistant. Your role is to answer questions accurately using the provided context from enterprise data sources.

INSTRUCTIONS:
1. Answer the question based ONLY on the provided context.
2. If the context does not contain enough information, say so clearly.
3. ALWAYS cite your sources using [Source N] notation matching the context references.
4. Be precise, professional, and concise.
5. If multiple sources agree, synthesize the information.
6. If sources conflict, note the discrepancy.
7. Never fabricate information not present in the context.

RESPONSE FORMAT:
- Provide a clear, well-structured answer
- Include [Source N] citations inline
- End with a brief "Sources Used" section listing the references
"""

RAG_USER_TEMPLATE = """Context:
{context}

---

Question: {query}

Please provide a comprehensive answer based on the context above, with proper citations."""


def build_rag_messages(query: str, context: str) -> List[LLMMessage]:
    """Build the message list for a RAG query."""
    return [
        LLMMessage(role="system", content=RAG_SYSTEM_PROMPT),
        LLMMessage(
            role="user",
            content=RAG_USER_TEMPLATE.format(context=context, query=query),
        ),
    ]

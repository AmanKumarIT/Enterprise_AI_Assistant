"""
Intelligent text and code chunking strategies.
Supports semantic paragraph chunking, recursive splitting,
and AST-aware code chunking.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Represents a single chunk of text with metadata."""
    content: str
    index: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_count: Optional[int] = None

    def __post_init__(self):
        self.token_count = self._estimate_tokens()

    def _estimate_tokens(self) -> int:
        return len(self.content.split()) * 4 // 3


class TextChunker:
    """
    Recursive character text splitter with overlap.
    Splits on paragraph/sentence/word boundaries, preferring
    natural breakpoints.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def chunk_text(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        if not text or not text.strip():
            return []

        base_metadata = metadata or {}
        raw_chunks = self._split_recursive(text, self.separators)

        chunks: List[Chunk] = []
        for idx, content in enumerate(raw_chunks):
            chunk_meta = {**base_metadata, "chunk_index": idx}
            chunks.append(Chunk(content=content, index=idx, metadata=chunk_meta))

        return chunks

    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        final_chunks: List[str] = []
        separator = separators[-1]

        for sep in separators:
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                break

        splits = text.split(separator) if separator else list(text)
        good_splits: List[str] = []
        current_len = 0

        for s in splits:
            piece = s if not separator else s
            piece_len = len(piece)

            if current_len + piece_len + (len(separator) if separator else 0) <= self.chunk_size:
                good_splits.append(piece)
                current_len += piece_len + (len(separator) if separator else 0)
            else:
                if good_splits:
                    merged = self._merge_splits(good_splits, separator)
                    final_chunks.extend(merged)
                    overlap_count = 0
                    while overlap_count < self.chunk_overlap and good_splits:
                        overlap_count += len(good_splits[-1]) + (len(separator) if separator else 0)
                        good_splits = good_splits[1:]
                    current_len = sum(len(s) for s in good_splits)

                if piece_len > self.chunk_size:
                    if len(separators) > 1:
                        sub_chunks = self._split_recursive(piece, separators[1:])
                        final_chunks.extend(sub_chunks)
                    else:
                        final_chunks.append(piece)
                else:
                    good_splits.append(piece)
                    current_len += piece_len

        if good_splits:
            merged = self._merge_splits(good_splits, separator)
            final_chunks.extend(merged)

        return [c.strip() for c in final_chunks if c.strip()]

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        merged = separator.join(splits)
        if len(merged) <= self.chunk_size:
            return [merged]
        return [merged]


class CodeChunker:
    """
    Code-aware chunker that respects function/class boundaries.
    Uses regex-based detection for Python, JavaScript, TypeScript, Java, Go, etc.
    """

    FUNCTION_PATTERNS = {
        "python": re.compile(
            r"^(class\s+\w+|def\s+\w+|async\s+def\s+\w+)", re.MULTILINE
        ),
        "javascript": re.compile(
            r"^(function\s+\w+|const\s+\w+\s*=\s*(?:async\s+)?\(|class\s+\w+|export\s+(?:default\s+)?(?:function|class|const))",
            re.MULTILINE,
        ),
        "typescript": re.compile(
            r"^(function\s+\w+|const\s+\w+\s*=\s*(?:async\s+)?\(|class\s+\w+|export\s+(?:default\s+)?(?:function|class|const|interface|type))",
            re.MULTILINE,
        ),
        "java": re.compile(
            r"^\s*(public|private|protected)?\s*(static)?\s*(class|interface|enum|void|\w+)\s+\w+",
            re.MULTILINE,
        ),
        "go": re.compile(r"^(func\s+\(?|type\s+\w+\s+struct)", re.MULTILINE),
    }

    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._text_chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def detect_language(self, filename: str) -> str:
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
        }
        for ext, lang in extension_map.items():
            if filename.endswith(ext):
                return lang
        return "generic"

    def chunk_code(
        self,
        code: str,
        filename: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        if not code or not code.strip():
            return []

        language = self.detect_language(filename)
        base_metadata = {**(metadata or {}), "language": language, "filename": filename}

        pattern = self.FUNCTION_PATTERNS.get(language)
        if not pattern:
            return self._text_chunker.chunk_text(code, base_metadata)

        blocks = self._split_by_definitions(code, pattern)
        chunks: List[Chunk] = []
        idx = 0

        for block in blocks:
            if len(block) <= self.chunk_size:
                chunk_meta = {**base_metadata, "chunk_index": idx}
                chunks.append(Chunk(content=block, index=idx, metadata=chunk_meta))
                idx += 1
            else:
                sub_chunks = self._text_chunker.chunk_text(block, base_metadata)
                for sc in sub_chunks:
                    sc.index = idx
                    sc.metadata["chunk_index"] = idx
                    chunks.append(sc)
                    idx += 1

        return chunks

    def _split_by_definitions(self, code: str, pattern: re.Pattern) -> List[str]:
        matches = list(pattern.finditer(code))
        if not matches:
            return [code] if code.strip() else []

        blocks: List[str] = []
        if matches[0].start() > 0:
            preamble = code[: matches[0].start()]
            if preamble.strip():
                blocks.append(preamble)

        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(code)
            block = code[start:end]
            if block.strip():
                blocks.append(block)

        return blocks

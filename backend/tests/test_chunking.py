"""
Unit tests for chunking strategies.
"""
import pytest
from app.services.chunking import TextChunker, CodeChunker


class TestTextChunker:
    def test_empty_text(self):
        chunker = TextChunker()
        assert chunker.chunk_text("") == []
        assert chunker.chunk_text("   ") == []

    def test_short_text(self):
        chunker = TextChunker(chunk_size=500)
        chunks = chunker.chunk_text("Hello world")
        assert len(chunks) == 1
        assert chunks[0].content == "Hello world"
        assert chunks[0].index == 0

    def test_long_text_splits(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = " ".join(["word"] * 200)
        chunks = chunker.chunk_text(text)
        assert len(chunks) > 1

    def test_metadata_propagation(self):
        chunker = TextChunker()
        chunks = chunker.chunk_text("Test", metadata={"source": "test"})
        assert chunks[0].metadata["source"] == "test"

    def test_token_count_estimation(self):
        chunker = TextChunker()
        chunks = chunker.chunk_text("one two three four five six")
        assert chunks[0].token_count > 0


class TestCodeChunker:
    def test_empty_code(self):
        chunker = CodeChunker()
        assert chunker.chunk_code("") == []

    def test_python_code_chunking(self):
        code = '''
def function_one():
    return 1

def function_two():
    return 2

class MyClass:
    def method(self):
        pass
'''
        chunker = CodeChunker(chunk_size=5000)
        chunks = chunker.chunk_code(code, filename="test.py")
        assert len(chunks) >= 1
        assert all(c.metadata.get("language") == "python" for c in chunks)

    def test_language_detection(self):
        chunker = CodeChunker()
        assert chunker.detect_language("app.py") == "python"
        assert chunker.detect_language("index.ts") == "typescript"
        assert chunker.detect_language("Main.java") == "java"
        assert chunker.detect_language("main.go") == "go"
        assert chunker.detect_language("style.css") == "generic"

    def test_large_code_gets_split(self):
        lines = [f"def func_{i}():\n    return {i}\n" for i in range(100)]
        large_code = "\n".join(lines)
        chunker = CodeChunker(chunk_size=500)
        chunks = chunker.chunk_code(large_code, filename="big.py")
        assert len(chunks) > 1

"""
GitHub repository ingestion pipeline.
Clones repos, traverses source files, applies code-aware chunking,
and tracks branch/commit metadata.
"""
import logging
import os
import shutil
import tempfile
import subprocess
from typing import List, Optional, Dict, Any

from app.ingestion.base import BaseIngestionPipeline, RawDocument
from app.services.chunking import CodeChunker

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift",
    ".kt", ".scala", ".sh", ".bash", ".yaml", ".yml", ".json",
    ".toml", ".cfg", ".ini", ".md", ".rst", ".txt", ".sql",
    ".html", ".css", ".scss", ".less", ".xml", ".proto",
    ".dockerfile", ".tf", ".hcl",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", "env",
    "dist", "build", ".next", ".nuxt", "vendor", "target",
    ".idea", ".vscode", ".vs", "bin", "obj",
}

MAX_FILE_SIZE_BYTES = 512 * 1024  # 512 KB per file


class GitHubIngestionPipeline(BaseIngestionPipeline):
    """
    Ingests a GitHub repository by cloning it locally,
    traversing source files, and chunking with code-awareness.

    Expected connection_config:
    {
        "repo_url": "https://github.com/org/repo.git",
        "branch": "main",
        "access_token": "ghp_...",  (optional for private repos)
        "include_patterns": ["*.py", "*.ts"],  (optional)
    }
    """

    def get_chunker(self):
        return CodeChunker(chunk_size=1500, chunk_overlap=200)

    async def extract_documents(self) -> List[RawDocument]:
        config = self.data_source.connection_config or {}
        repo_url: str = config.get("repo_url", "")
        branch: str = config.get("branch", "main")
        access_token: Optional[str] = config.get("access_token")

        if not repo_url:
            raise ValueError("Missing repo_url in connection_config")

        clone_url = repo_url
        if access_token and "github.com" in repo_url:
            clone_url = repo_url.replace(
                "https://", f"https://x-access-token:{access_token}@"
            )

        clone_dir = tempfile.mkdtemp(prefix="eka_github_")
        try:
            logger.info("Cloning %s (branch: %s) into %s", repo_url, branch, clone_dir)
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, clone_url, clone_dir],
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )

            commit_hash = subprocess.run(
                ["git", "-C", clone_dir, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            ).stdout.strip()

            raw_docs: List[RawDocument] = []
            for root, dirs, files in os.walk(clone_dir):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

                for filename in files:
                    filepath = os.path.join(root, filename)
                    ext = os.path.splitext(filename)[1].lower()

                    if ext not in SUPPORTED_EXTENSIONS:
                        continue

                    try:
                        size = os.path.getsize(filepath)
                        if size > MAX_FILE_SIZE_BYTES or size == 0:
                            continue

                        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()

                        relative_path = os.path.relpath(filepath, clone_dir)
                        raw_docs.append(
                            RawDocument(
                                title=relative_path,
                                content=content,
                                source_uri=f"{repo_url}/blob/{branch}/{relative_path}",
                                metadata={
                                    "repo_url": repo_url,
                                    "branch": branch,
                                    "commit": commit_hash,
                                    "file_path": relative_path,
                                    "extension": ext,
                                    "file_size": size,
                                },
                                mime_type=f"text/{ext.lstrip('.')}",
                            )
                        )
                    except Exception as e:
                        logger.warning("Skipping file %s: %s", filepath, str(e))

            logger.info(
                "Extracted %d files from %s (branch: %s, commit: %s)",
                len(raw_docs),
                repo_url,
                branch,
                commit_hash,
            )
            return raw_docs

        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

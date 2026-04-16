"""
SQL database ingestion pipeline.
Introspects schemas, summarizes tables, embeds sample rows,
and provides natural-language-to-SQL support via metadata.
"""
import logging
from typing import List, Optional, Dict, Any

from sqlalchemy import create_engine, inspect, text as sql_text

from app.ingestion.base import BaseIngestionPipeline, RawDocument
from app.services.chunking import TextChunker

logger = logging.getLogger(__name__)

MAX_SAMPLE_ROWS = 5
MAX_TABLES = 200


class SQLIngestionPipeline(BaseIngestionPipeline):
    """
    Introspects a SQL database, generates schema summaries and sample
    rows for embedding, enabling natural language queries over structured data.

    Expected connection_config:
    {
        "connection_string": "postgresql://user:pass@host:5432/dbname",
        "schema": "public",  (optional)
        "include_tables": ["orders", "customers"],  (optional)
        "exclude_tables": ["migrations"],  (optional)
    }
    """

    def get_chunker(self):
        return TextChunker(chunk_size=1200, chunk_overlap=150)

    async def extract_documents(self) -> List[RawDocument]:
        config = self.data_source.connection_config or {}
        conn_string: str = config.get("connection_string", "")
        schema_name: str = config.get("schema", "public")
        include_tables: Optional[List[str]] = config.get("include_tables")
        exclude_tables: List[str] = config.get("exclude_tables", [])

        if not conn_string:
            raise ValueError("Missing connection_string in connection_config")

        engine = create_engine(conn_string)
        inspector = inspect(engine)

        table_names = inspector.get_table_names(schema=schema_name)
        if include_tables:
            table_names = [t for t in table_names if t in include_tables]
        table_names = [t for t in table_names if t not in exclude_tables]
        table_names = table_names[:MAX_TABLES]

        raw_docs: List[RawDocument] = []

        full_schema_parts = [f"Database Schema: {conn_string.split('/')[-1]}\n"]

        for table_name in table_names:
            try:
                columns = inspector.get_columns(table_name, schema=schema_name)
                pk = inspector.get_pk_constraint(table_name, schema=schema_name)
                fks = inspector.get_foreign_keys(table_name, schema=schema_name)
                indexes = inspector.get_indexes(table_name, schema=schema_name)

                col_descriptions = []
                for col in columns:
                    nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                    default_val = col.get("default", "")
                    default_str = f" DEFAULT {default_val}" if default_val else ""
                    col_descriptions.append(
                        f"  - {col['name']} ({col['type']}) {nullable}{default_str}"
                    )

                pk_str = f"  Primary Key: ({', '.join(pk.get('constrained_columns', []))})"
                fk_lines = []
                for fk in fks:
                    fk_cols = ", ".join(fk.get("constrained_columns", []))
                    ref_table = fk.get("referred_table", "?")
                    ref_cols = ", ".join(fk.get("referred_columns", []))
                    fk_lines.append(f"  FK: ({fk_cols}) -> {ref_table}({ref_cols})")

                index_lines = []
                for idx in indexes:
                    idx_cols = ", ".join(idx.get("column_names", []))
                    unique = "UNIQUE " if idx.get("unique") else ""
                    index_lines.append(f"  {unique}INDEX {idx['name']} ({idx_cols})")

                schema_text = f"Table: {schema_name}.{table_name}\nColumns:\n"
                schema_text += "\n".join(col_descriptions)
                schema_text += f"\n{pk_str}"
                if fk_lines:
                    schema_text += "\nForeign Keys:\n" + "\n".join(fk_lines)
                if index_lines:
                    schema_text += "\nIndexes:\n" + "\n".join(index_lines)

                full_schema_parts.append(schema_text)

                sample_text = ""
                try:
                    with engine.connect() as conn:
                        result = conn.execute(
                            sql_text(f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT {MAX_SAMPLE_ROWS}')
                        )
                        rows = result.fetchall()
                        col_names = list(result.keys())
                        if rows:
                            sample_text = f"\nSample data from {table_name}:\n"
                            sample_text += " | ".join(col_names) + "\n"
                            for row in rows:
                                sample_text += " | ".join(str(v)[:50] for v in row) + "\n"
                except Exception as e:
                    logger.warning("Could not fetch sample rows from %s: %s", table_name, str(e))

                doc_content = schema_text + sample_text
                raw_docs.append(
                    RawDocument(
                        title=f"Table: {schema_name}.{table_name}",
                        content=doc_content,
                        source_uri=f"sql://{schema_name}.{table_name}",
                        metadata={
                            "table_name": table_name,
                            "schema": schema_name,
                            "column_count": len(columns),
                            "has_primary_key": bool(pk.get("constrained_columns")),
                            "foreign_key_count": len(fks),
                        },
                    )
                )

            except Exception as e:
                logger.error("Failed to introspect table %s: %s", table_name, str(e))

        if full_schema_parts:
            full_schema = "\n\n".join(full_schema_parts)
            raw_docs.insert(
                0,
                RawDocument(
                    title="Full Database Schema",
                    content=full_schema,
                    source_uri=f"sql://schema_overview",
                    metadata={"type": "schema_overview", "table_count": len(table_names)},
                ),
            )

        engine.dispose()
        logger.info("Extracted %d documents from SQL database", len(raw_docs))
        return raw_docs

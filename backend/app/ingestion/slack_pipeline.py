"""
Slack ingestion pipeline.
Syncs channels, threads, and messages using the Slack Web API.
Supports incremental sync via timestamp tracking.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from app.ingestion.base import BaseIngestionPipeline, RawDocument
from app.services.chunking import TextChunker

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_CHANNEL = 5000


class SlackIngestionPipeline(BaseIngestionPipeline):
    """
    Syncs Slack messages from configured channels.

    Expected connection_config:
    {
        "bot_token": "xoxb-...",
        "channels": ["C01ABCDEF", "general"],  (optional - syncs all if omitted)
        "oldest_timestamp": "1609459200",  (optional - for incremental sync)
    }
    """

    def get_chunker(self):
        return TextChunker(chunk_size=800, chunk_overlap=100)

    async def extract_documents(self) -> List[RawDocument]:
        try:
            from slack_sdk import WebClient
            from slack_sdk.errors import SlackApiError
        except ImportError:
            raise ImportError("slack_sdk is required for Slack ingestion. Install with: pip install slack_sdk")

        config = self.data_source.connection_config or {}
        bot_token: str = config.get("bot_token", "")
        channel_filter: Optional[List[str]] = config.get("channels")
        oldest: str = config.get("oldest_timestamp", "0")

        if not bot_token:
            raise ValueError("Missing bot_token in connection_config")

        client = WebClient(token=bot_token)
        raw_docs: List[RawDocument] = []

        try:
            channels_response = client.conversations_list(
                types="public_channel,private_channel", limit=200
            )
            channels = channels_response.get("channels", [])

            if channel_filter:
                channels = [
                    ch for ch in channels
                    if ch["id"] in channel_filter or ch["name"] in channel_filter
                ]

            for channel in channels:
                channel_id = channel["id"]
                channel_name = channel.get("name", channel_id)

                try:
                    messages: List[Dict[str, Any]] = []
                    cursor = None

                    while len(messages) < MAX_MESSAGES_PER_CHANNEL:
                        kwargs = {
                            "channel": channel_id,
                            "limit": 200,
                            "oldest": oldest,
                        }
                        if cursor:
                            kwargs["cursor"] = cursor

                        history = client.conversations_history(**kwargs)
                        batch = history.get("messages", [])
                        messages.extend(batch)

                        if not history.get("has_more"):
                            break
                        cursor = history.get("response_metadata", {}).get("next_cursor")

                    thread_messages: Dict[str, List[Dict[str, Any]]] = {}
                    for msg in messages:
                        if msg.get("thread_ts") and msg.get("reply_count", 0) > 0:
                            try:
                                replies = client.conversations_replies(
                                    channel=channel_id,
                                    ts=msg["thread_ts"],
                                    limit=100,
                                )
                                thread_messages[msg["thread_ts"]] = replies.get("messages", [])
                            except SlackApiError as e:
                                logger.warning(
                                    "Failed to fetch thread %s: %s", msg["thread_ts"], str(e)
                                )

                    conversation_blocks = self._group_messages_into_blocks(
                        messages, thread_messages, channel_name
                    )

                    for idx, block in enumerate(conversation_blocks):
                        raw_docs.append(
                            RawDocument(
                                title=f"#{channel_name} - Block {idx + 1}",
                                content=block["content"],
                                source_uri=f"slack://{channel_id}/{block.get('ts', '')}",
                                metadata={
                                    "channel_id": channel_id,
                                    "channel_name": channel_name,
                                    "message_count": block["message_count"],
                                    "date_range": block.get("date_range", ""),
                                },
                            )
                        )

                    logger.info(
                        "Extracted %d message blocks from #%s",
                        len(conversation_blocks),
                        channel_name,
                    )

                except SlackApiError as e:
                    logger.error(
                        "Failed to fetch messages from #%s: %s", channel_name, str(e)
                    )

        except SlackApiError as e:
            raise RuntimeError(f"Failed to list Slack channels: {str(e)}")

        logger.info("Total Slack documents extracted: %d", len(raw_docs))
        return raw_docs

    def _group_messages_into_blocks(
        self,
        messages: List[Dict[str, Any]],
        thread_messages: Dict[str, List[Dict[str, Any]]],
        channel_name: str,
    ) -> List[Dict[str, Any]]:
        """Group messages into conversational blocks for better embedding context."""
        messages.sort(key=lambda m: float(m.get("ts", 0)))
        blocks: List[Dict[str, Any]] = []
        current_lines: List[str] = []
        current_count = 0
        block_start_ts = ""
        max_block_chars = 3000

        for msg in messages:
            ts = msg.get("ts", "")
            user = msg.get("user", "unknown")
            text = msg.get("text", "").strip()
            if not text:
                continue

            if not block_start_ts:
                block_start_ts = ts

            timestamp_str = ""
            try:
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError):
                pass

            line = f"[{timestamp_str}] {user}: {text}"
            current_lines.append(line)
            current_count += 1

            if ts in thread_messages:
                for reply in thread_messages[ts][1:]:
                    reply_user = reply.get("user", "unknown")
                    reply_text = reply.get("text", "").strip()
                    if reply_text:
                        current_lines.append(f"  ↳ {reply_user}: {reply_text}")
                        current_count += 1

            total_chars = sum(len(l) for l in current_lines)
            if total_chars >= max_block_chars:
                content = f"Channel: #{channel_name}\n\n" + "\n".join(current_lines)
                blocks.append({
                    "content": content,
                    "message_count": current_count,
                    "ts": block_start_ts,
                    "date_range": f"{block_start_ts} - {ts}",
                })
                current_lines = []
                current_count = 0
                block_start_ts = ""

        if current_lines:
            content = f"Channel: #{channel_name}\n\n" + "\n".join(current_lines)
            blocks.append({
                "content": content,
                "message_count": current_count,
                "ts": block_start_ts,
            })

        return blocks

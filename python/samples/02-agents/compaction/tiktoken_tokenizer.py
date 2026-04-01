# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "tiktoken",
# ]
# ///
# Run with: uv run samples/02-agents/compaction/tiktoken_tokenizer.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

import tiktoken  # type: ignore
from agent_framework import (
    Message,
    TokenizerProtocol,
    TruncationStrategy,
    annotate_message_groups,
    apply_compaction,
    included_token_count,
)

"""This sample demonstrates a custom TokenizerProtocol implementation with tiktoken.

Key components:
- `TiktokenTokenizer` backed by `tiktoken`
- Token-based `TruncationStrategy` (`max_n` / `compact_to`)
- Inspecting projected roles and remaining included token count
"""


class TiktokenTokenizer(TokenizerProtocol):
    """TokenizerProtocol implementation backed by tiktoken's o200k_base (gpt-4.1 and up default) encoding."""

    def __init__(self, *, encoding_name: str = "o200k_base", model_name: str | None = None) -> None:
        if model_name is not None:
            self._encoding = tiktoken.encoding_for_model(model_name)
        else:
            self._encoding: Any = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))


def _build_messages() -> list[Message]:
    return [
        Message(role="system", text="You are a migration assistant."),
        Message(
            role="user",
            text="List all migration risks and include detailed mitigations for each risk category.",
        ),
        Message(
            role="assistant",
            text=(
                "Primary risks include schema drift, missing foreign key constraints, "
                "and data quality regressions. Mitigations include staged validation, "
                "shadow writes, and replay-based verification."
            ),
        ),
        Message(
            role="user",
            text=("Now provide a detailed checklist with owners, rollback gates, and validation criteria."),
        ),
        Message(
            role="assistant",
            text=(
                "Checklist: baseline snapshots, migration dry-run, production "
                "canary, progressive deployment, automated integrity checks, and "
                "post-migration reconciliation."
            ),
        ),
    ]


async def main() -> None:
    # 1. Create a tokenizer implementation that uses tiktoken.
    tokenizer = TiktokenTokenizer()

    # 2. Configure token-based truncation.
    strategy = TruncationStrategy(
        max_n=250,
        compact_to=150,
        tokenizer=tokenizer,
        preserve_system=True,
    )

    # 3. Build conversation and measure token count before compaction.
    messages = _build_messages()
    annotate_message_groups(messages, tokenizer=tokenizer)
    token_count_before = included_token_count(messages)

    # 4. Apply compaction and measure token count after compaction.
    projected = await apply_compaction(messages, strategy=strategy, tokenizer=tokenizer)
    token_count_after = included_token_count(messages)

    # 5. Print before/after token counts and projected conversation.
    print(f"Projected messages: {len(projected)}")
    print(f"Included token count before compaction: {token_count_before}")
    print(f"Included token count after compaction: {token_count_after}")
    print("Projected roles:", [message.role for message in projected])
    for message in projected:
        token_count = message.additional_properties.get("_group", {}).get("token_count")
        print(f"- [{message.role}] {message.text} ({token_count} tokens)")


if __name__ == "__main__":
    asyncio.run(main())

"""
Projected messages: 3
Included token count before compaction: 263
Included token count after compaction: 149
Projected roles: ['system', 'user', 'assistant']
- [system] You are a migration assistant. (40 tokens)
- [user] Now provide a detailed checklist with owners, rollback gates, and validation criteria. (49 tokens)
- [assistant] Checklist: baseline snapshots, migration dry-run, production canary,
  progressive deployment, automated integrity checks, and post-migration reconciliation. (60 tokens)
"""

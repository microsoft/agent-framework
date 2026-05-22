# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import (
    CharacterEstimatorTokenizer,
    ChatResponse,
    Message,
    SelectiveToolCallCompactionStrategy,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    annotate_message_groups,
    apply_compaction,
    included_token_count,
)

"""This sample demonstrates composed in-run compaction with a token budget.

Key components:
- TokenBudgetComposedStrategy
- Sequential strategy composition
- Summarization with a SupportsChatGetResponse-compatible summarizer client
"""


class BudgetSummaryClient:
    async def get_response(
        self,
        messages: list[Message],
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        summary_text = f"Budget summary generated from {len(messages)} prompt messages."
        return ChatResponse(messages=[Message(role="assistant", contents=[summary_text])])


def _build_long_history() -> list[Message]:
    history = [Message(role="system", contents=["You are a migration copilot."])]
    for i in range(1, 8):
        history.append(
            Message(
                role="user",
                contents=[f"Iteration {i}: capture migration requirements and edge cases."],
            )
        )
        history.append(
            Message(
                role="assistant",
                contents=[
                    (
                        f"Iteration {i}: detailed plan with dependencies, rollback guidance, and testing details. "
                        "This sentence is intentionally long to create token pressure."
                    )
                ],
            )
        )
    return history


async def main() -> None:
    # 1. Build synthetic history representing long-running in-run growth.
    messages = _build_long_history()

    # 2. Configure tokenizer and measure token count before compaction.
    tokenizer = CharacterEstimatorTokenizer()
    annotate_message_groups(messages, tokenizer=tokenizer)
    budget_before = included_token_count(messages)

    # 3. Configure composed strategy stack.
    composed = TokenBudgetComposedStrategy(
        token_budget=200,
        tokenizer=tokenizer,
        strategies=[
            SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0),
            SummarizationStrategy(
                client=BudgetSummaryClient(),
                target_count=3,
                threshold=3,
            ),
            SlidingWindowStrategy(keep_last_groups=4),
        ],
    )

    # 4. Apply compaction and inspect the budget result.
    projected = await apply_compaction(messages, strategy=composed, tokenizer=tokenizer)
    budget_after = included_token_count(messages)

    print(f"Projected messages after compaction: {len(projected)}")
    print(f"Included token count before compaction: {budget_before}")
    print(f"Included token count after compaction: {budget_after}")
    print("Projected roles:", [m.role for m in projected])
    print("Projected messages with token counts:")
    for msg in projected:
        group = msg.additional_properties.get("_group")
        token_count = group.get("token_count") if isinstance(group, dict) else None
        text_preview = msg.text[:80] if msg.text else "<non-text>"
        print(f"- [{msg.role}] {text_preview} ({token_count} tokens)")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Projected messages after compaction: 3
Included token count before compaction: 793
Included token count after compaction: 144
Projected roles: ['system', 'user', 'assistant']
Projected messages with token counts:
- [system] You are a migration copilot. (35 tokens)
- [user] Iteration 7: capture migration requirements and edge cases. (43 tokens)
- [assistant] Iteration 7: detailed plan with dependencies, rollback guidance, and testing det (66 tokens)
"""

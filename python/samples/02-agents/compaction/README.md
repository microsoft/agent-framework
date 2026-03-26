# Context Compaction Samples

This folder demonstrates context compaction patterns introduced by ADR-0019.

## Files

- `basics.py` — builds a local message list and applies each built-in strategy one at a time.
- `advanced.py` — composes multiple strategies with `TokenBudgetComposedStrategy`.
- `agent_client_overrides.py` — shows client defaults, agent-level overrides, and per-run compaction overrides.
- `custom.py` — defines a custom strategy implementing the `CompactionStrategy` protocol.
- `tiktoken_tokenizer.py` — shows a `TokenizerProtocol` implementation backed by `tiktoken`.
- `compaction_provider.py` — uses `CompactionProvider` with an agent and `InMemoryHistoryProvider`.

Run samples with:

```bash
uv run samples/02-agents/compaction/basics.py
uv run samples/02-agents/compaction/advanced.py
uv run samples/02-agents/compaction/agent_client_overrides.py
uv run samples/02-agents/compaction/custom.py
uv run samples/02-agents/compaction/tiktoken_tokenizer.py
uv run samples/02-agents/compaction/compaction_provider.py  # requires OPENAI_API_KEY
```

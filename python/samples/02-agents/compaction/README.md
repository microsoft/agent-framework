# Context Compaction Samples

This folder demonstrates context compaction patterns introduced by ADR-0019.

## Files

- `basics.py` — builds a local message list and applies each built-in in-run strategy.
- `advanced.py` — composes multiple strategies with `TokenBudgetComposedStrategy`.
- `custom.py` — defines a custom strategy implementing the `CompactionStrategy` protocol.
- `tiktoken_tokenizer.py` — shows a `TokenizerProtocol` implementation backed by `tiktoken`.
- `storage.py` — planned for Phase 2 (history/storage compaction and `upsert` flow).

Run samples with:

```bash
uv run samples/02-agents/compaction/basics.py
uv run samples/02-agents/compaction/advanced.py
uv run samples/02-agents/compaction/custom.py
uv run samples/02-agents/compaction/tiktoken_tokenizer.py
```

# TaskMarket delegation sample

This sample gives an Agent Framework agent two read-only tools for evaluating
whether work should be delegated to [TaskMarket](https://taskmarket.dev/):

- `discover_taskmarket_tasks` searches open public tasks by text, reward, and limit.
- `inspect_taskmarket_task` retrieves one exact task after validating its ID.

The sample does not claim, bid, submit, create, accept, sign, or spend. Task
descriptions are external, untrusted content. A production delegation flow
must add an explicit user-approval step and an independently authorized
payment/signing client.

## Run

From `python/` in this repository:

```bash
pip install -e packages/core -e packages/openai python-dotenv
export OPENAI_API_KEY=...
python samples/02-agents/tools/taskmarket_delegation.py
```

No TaskMarket account, API token, wallet, or payment is required for discovery.
The model provider key is only needed to run the conversational agent; the
underlying public API client is standard-library Python.

## Offline checks

```bash
python3 -m unittest discover -s samples/02-agents/tools -p 'test_taskmarket_client.py'
python3 -m py_compile samples/02-agents/tools/taskmarket_client.py samples/02-agents/tools/taskmarket_delegation.py
```

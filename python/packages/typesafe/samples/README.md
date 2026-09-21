# TypeSafe AI samples

These samples need extra explanation because TypeSafe System One models return
typed judgments rather than ordinary generated chat text.

## Samples

| Sample | What it demonstrates | Expected output |
| --- | --- | --- |
| [`jev_structured_output.py`](jev_structured_output.py) | Direct client and Agent use with Noul, Choice, and Score questions. | Department, confidence, frustration score, and urgency probability. |
| [`function_calling.py`](function_calling.py) | Sequential local tool calls followed by a final Choice comparison. | Two weather tool results, the selected better city, and Choice confidence. |
| [`mcp_function_calling.py`](mcp_function_calling.py) | MCP discovery, TypeSafe tool routing, and terminal Noul evaluation. | The MCP weather result and success probability. |
| [`mcp_weather_server.py`](mcp_weather_server.py) | The local stdio MCP server used by the MCP client sample. | MCP protocol traffic only; the client prints the user-facing result. |

## How `response_format` works

Regular chat clients commonly use `response_format` to provide a Pydantic output
model or JSON schema. This connector instead expects a TypeSafe `Questions`
mapping:

```python
options = {
    "response_format": {
        "urgent": Noul(instructions="Does this need urgent attention?"),
        "department": Choice(
            instructions="Which department should handle this?",
            criteria={"billing": None, "technical": None},
        ),
        "severity": Score(
            instructions="How severe is the issue?",
            criteria=["Low", "Medium", "High"],
        ),
    }
}
```

The configured keys become answer IDs on `SystemOneResponse`:

| Question | Meaning | Main result fields |
| --- | --- | --- |
| `Noul` | Probability that a statement is true or the answer is yes. | `noul` from 0 to 1. There is no separate confidence field. |
| `Choice` | Select one label from a closed set. | `choice`, `probabilities`, and `confidence`. |
| `Score` | Rate along ordered rubric levels. | Weighted `score`, `legend`, `probabilities`, and `confidence`. |

For every sample, `response.value` is the complete typed
`SystemOneResponse`, including `answers`, the grouped `nouls`/`choices`/`scores`
views, model name, and token usage.

`response.text` depends on the run:

- Without tools, it is the serialized `SystemOneResponse` JSON.
- With tools, it is a convenience string containing the current turn's tool
  results followed by final `Choice` and `Score` decisions.
- `Noul` probabilities are not appended to tool-run text. Read them from
  `response.value.nouls`.

Temporary questions used internally for tool routing are removed from the final
`SystemOneResponse`.

## Setup and run

Set `TYPESAFE_API_KEY` in `python/.env`. The Python samples also call
`load_dotenv()`, so the key is loaded when running them directly from `python/`.

Run from `python/`:

```bash
uv run --env-file .env --package agent-framework-typesafe \
    python packages/typesafe/samples/jev_structured_output.py

uv run --env-file .env --package agent-framework-typesafe \
    python packages/typesafe/samples/function_calling.py

uv run --with "mcp>=1.27.0,<2" --env-file .env --package agent-framework-typesafe \
    python packages/typesafe/samples/mcp_function_calling.py
```

The MCP command explicitly installs the sample-only `mcp` dependency. The MCP
sample launches and closes the stdio server automatically.

Each source file contains a representative output block at the end. Jev
probabilities, confidence, random sample temperatures, and resulting comparisons
can vary between runs.

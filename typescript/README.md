# Microsoft Agent Framework for TypeScript

> [!IMPORTANT]
> This directory is an initial source preview. It establishes the TypeScript package layout and core agent execution path; it does not yet have feature parity with the Python or .NET SDKs.

## Packages

| Package                             | Description                                                                                                               |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `@microsoft/agent-framework-core`   | Provider-neutral agents, chat clients, messages, streaming responses, middleware, function tools, and in-memory sessions. |
| `@microsoft/agent-framework-openai` | OpenAI Chat Completions adapter built on the official `openai` package.                                                   |

The initial port supports:

- streaming and non-streaming agent runs;
- JSON Schema-validated function tools;
- ordered parallel tool execution with stable call occurrence IDs;
- agent, chat, and function middleware;
- session-scoped in-memory conversation history;
- OpenAI Chat Completions, including streaming tool calls.

Approvals, durable stores, MCP, workflows, vector stores, hosted tools, telemetry, and additional providers remain future work. These APIs are intentionally absent rather than represented by incomplete compatibility shims.

## Development

Node.js 22.12 or later is required.

```bash
cd typescript
npm ci
npm run check
```

Run the quickstart after setting `OPENAI_API_KEY` and `OPENAI_CHAT_MODEL`:

```bash
npm run build
npm run sample
```

See [the getting-started sample](samples/getting-started.ts) and the package READMEs for API details.

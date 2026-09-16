# `@microsoft/agent-framework-openai`

OpenAI Chat Completions support for Microsoft Agent Framework's TypeScript SDK.

```ts
import { Agent } from "@microsoft/agent-framework-core";
import { OpenAIChatCompletionClient } from "@microsoft/agent-framework-openai";

const agent = new Agent({
  client: new OpenAIChatCompletionClient({ model: process.env.OPENAI_CHAT_MODEL }),
  instructions: "You are a concise assistant.",
});

console.log((await agent.run("Hello")).text);
```

The client uses `OPENAI_API_KEY` through the official `openai` package. Pass an existing `OpenAI` or `AzureOpenAI` instance as `client` to control authentication, endpoints, retries, and transport behavior.

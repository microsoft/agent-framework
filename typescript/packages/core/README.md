# `@microsoft/agent-framework-core`

Provider-neutral TypeScript primitives for Microsoft Agent Framework.

## Agent and tools

```ts
import { Agent, defineTool } from "@microsoft/agent-framework-core";

const weather = defineTool({
  name: "get_weather",
  description: "Get the current weather for a city.",
  parameters: {
    type: "object",
    properties: { city: { type: "string" } },
    required: ["city"],
    additionalProperties: false,
  },
  execute: ({ city }) => `${String(city)}: sunny`,
});

const agent = new Agent({
  client,
  instructions: "Be concise.",
  tools: [weather],
});

const session = agent.createSession();
const response = await agent.run("What is the weather in Seattle?", { session });
console.log(response.text);
```

`client` can be any object implementing `SupportsChatGetResponse`. Extend `BaseChatClient` to get middleware, response streaming, and automatic function invocation.

Tool parameters use explicit JSON Schema and are validated with Ajv immediately before execution. Host values supplied through `functionInvocationArguments` remain separate from model arguments and are available as `context.runtimeArguments` inside tools and function middleware.

## Streaming

```ts
const stream = agent.run("Tell me a story.", { stream: true });

for await (const update of stream) {
  process.stdout.write(update.text);
}

const finalResponse = await stream.getFinalResponse();
```

A `ResponseStream` retains updates and finalizes them once. Do not consume the same stream concurrently.

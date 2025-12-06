# Agent Framework with OpenAI

These samples show how to use the Agent Framework with the OpenAI exchange types.

By default, the .Net version of Agent Framework uses the [Microsoft.Extensions.AI.Abstractions](https://www.nuget.org/packages/Microsoft.Extensions.AI.Abstractions/) exchange types.

For developers who are using the [OpenAI SDK](https://www.nuget.org/packages/OpenAI) this can be problematic because there are conflicting exchange types which can cause confusion.

Agent Framework provides additional support to allow OpenAI developers to use the OpenAI exchange types.

|Sample|Description|
|---|---|
|[Creating an AIAgent](./Agent_OpenAI_Step01_Running/)|This sample demonstrates how to create and run a basic agent with native OpenAI SDK types. Shows both regular and streaming invocation of the agent.|
|[Using Reasoning Capabilities](./Agent_OpenAI_Step02_Reasoning/)|This sample demonstrates how to create an AI agent with reasoning capabilities using OpenAI's reasoning models and response types.|
|[Creating an Agent from a ChatClient](./Agent_OpenAI_Step03_CreateFromChatClient/)|This sample demonstrates how to create an AI agent directly from an OpenAI.Chat.ChatClient instance using OpenAIChatClientAgent.|
|[Creating an Agent from an OpenAIResponseClient](./Agent_OpenAI_Step04_CreateFromOpenAIResponseClient/)|This sample demonstrates how to create an AI agent directly from an OpenAI.Responses.OpenAIResponseClient instance using OpenAIResponseClientAgent.|
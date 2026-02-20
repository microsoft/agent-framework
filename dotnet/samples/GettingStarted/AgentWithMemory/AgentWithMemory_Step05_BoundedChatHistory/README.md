# Bounded Chat History with Vector Store Overflow

This sample demonstrates how to create a custom `ChatHistoryProvider` that keeps a bounded window of recent messages in session state and automatically overflows older messages to a vector store. When the agent is invoked, it searches the vector store for relevant older messages and prepends them as memory context.

## Concepts

- **`TruncatingChatReducer`**: A custom `IChatReducer` that keeps the most recent N messages and exposes removed messages via a `RemovedMessages` property.
- **`BoundedChatHistoryProvider`**: A custom `ChatHistoryProvider` that composes:
  - `InMemoryChatHistoryProvider` for fast session-state storage (bounded by the reducer)
  - `ChatHistoryMemoryProvider` for vector-store overflow and semantic search of older messages

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure OpenAI resource with:
  - A chat deployment (e.g., `gpt-4o-mini`)
  - An embedding deployment (e.g., `text-embedding-3-large`)

## Configuration

Set the following environment variables:

| Variable | Description | Default |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL | *(required)* |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Chat model deployment name | `gpt-4o-mini` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` | Embedding model deployment name | `text-embedding-3-large` |

## Running the Sample

```bash
dotnet run
```

## How it Works

1. The agent starts a conversation with a bounded session window of 4 messages.
2. As messages accumulate beyond the limit, the `TruncatingChatReducer` removes the oldest messages.
3. The `BoundedChatHistoryProvider` detects the removed messages and stores them in a vector store via `ChatHistoryMemoryProvider`.
4. On subsequent invocations, the provider searches the vector store for relevant older messages and prepends them as memory context, allowing the agent to recall information from earlier in the conversation.

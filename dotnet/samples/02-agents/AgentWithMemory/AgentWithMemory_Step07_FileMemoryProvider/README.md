# File Based Memory with FileMemoryProvider

This sample demonstrates how to give an agent file-based memory using the `FileMemoryProvider`.

The `FileMemoryProvider` is an `AIContextProvider` that exposes a set of memory tools to the agent, allowing the agent to decide what to remember and when to recall it. Each memory is stored as an individual file in an `AgentFileStore`, so memories survive beyond the lifetime of a single conversation.

## Concepts

- **`FileMemoryProvider`**: An `AIContextProvider` that adds the following tools to the agent:

  | Tool | Description |
  |---|---|
  | `file_memory_write` | Write a memory file with a name, content and optional description. |
  | `file_memory_read` | Read the content of a memory file by name. |
  | `file_memory_delete` | Delete a memory file by name. |
  | `file_memory_ls` | List all memory files with their descriptions. |
  | `file_memory_grep` | Search memory file contents using a regular expression. |
  | `file_memory_replace` | Replace occurrences of a substring within a memory file. |
  | `file_memory_replace_lines` | Replace whole lines within a memory file. |

  The provider also maintains a `memories.md` index file, which it injects into the conversation so the agent knows which memories are available without having to list them first.

- **`AgentFileStore`**: The pluggable storage abstraction used by the provider. This sample uses `FileSystemAgentFileStore` to store memories on the local disk, but `InMemoryAgentFileStore` or a custom implementation (e.g. backed by blob storage) can be used instead.

- **`FileMemoryState`**: The per-session state of the provider. Its `WorkingFolder` property determines the folder, relative to the store root, that memory files are written to.

## Configuring the memory folder

By default, all sessions share the root folder of the store, which means every session reads and writes the same flat set of memory files.

To scope memories, e.g. per user, per tenant or per session, pass a state initializer callback to the `FileMemoryProvider` constructor. The callback receives the `AgentSession` and is invoked whenever the provider cannot find existing state in that session, i.e. typically the first time the provider is used with a new session:

```csharp
using var fileMemoryProvider = new FileMemoryProvider(
    fileStore,
    session => new FileMemoryState { WorkingFolder = $"users/{userId}" });
```

In this sample, memories are written to `agent-memory/users/UID1` under the application's base directory. Because the folder is derived from a fixed user id rather than the session, a new session for the same user picks up the memories written by earlier sessions.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- A Microsoft Foundry project with a chat model deployment
- Run `az login` to authenticate with `DefaultAzureCredential`

## Configuration

Set the following environment variables:

| Variable | Description | Default |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Your Foundry project endpoint | *(required)* |
| `FOUNDRY_MODEL` | Chat model deployment name | `gpt-5.4-mini` |

## Running the Sample

```bash
dotnet run
```

## How it Works

1. A `FileSystemAgentFileStore` is created, rooted at a local `agent-memory` folder.
2. A `FileMemoryProvider` is created over that store, with a state initializer that puts the memories for the current user in their own working folder.
3. The provider is attached to the agent via `ChatClientAgentOptions.AIContextProviders`, which gives the agent the `file_memory_*` tools and instructions for using them.
4. In the first conversation, the user shares some preferences and the agent calls `file_memory_write` to store them as a file in the working folder. The sample then lists the files that were created on disk.
5. In the second conversation, a brand new session is created with no chat history from the first conversation. The provider injects the memory index into the conversation, and the agent calls `file_memory_read` to recall the stored preferences when making its recommendations.

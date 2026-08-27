# Declarative workflow file input

This sample demonstrates how to provide file-based input to a declarative workflow. It uploads a local file to the Foundry project, converts the uploaded file reference into a `ChatMessage` with both `TextContent` and `HostedFileContent`, then starts a YAML-defined workflow with that message.

The workflow displays `System.LastMessage.Text`, then invokes a Foundry-backed agent in the same workflow conversation so the uploaded file is available to the agent.

## Run the sample

Configure the common declarative workflow settings described in the parent [README](../README.md), then run:

```pwsh
dotnet run
```

By default the sample uses `ProductBrief.txt` from this project. To provide a different file and prompt:

```pwsh
dotnet run "C:\path\to\document.pdf" "Summarize this document for an executive audience."
```

The important part is that the file is not passed as plain text. The program uploads the file, creates a `ChatMessage` whose content includes the prompt and uploaded file reference, and starts the workflow with that message. The YAML invokes the agent with `conversationId: =System.ConversationId` so the agent sees the same conversation item that contains the file.

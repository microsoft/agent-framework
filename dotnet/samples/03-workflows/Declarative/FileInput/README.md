# Declarative workflow file input

This sample demonstrates how to provide file-based input to a declarative workflow. It uploads the bundled `ProductBrief.txt` file to the Foundry project, converts the uploaded file reference into a `ChatMessage` with both `TextContent` and `HostedFileContent`, then starts a YAML-defined workflow with that message.

The workflow displays `System.LastMessage.Text`, then invokes a Foundry-backed agent in the same workflow conversation so the uploaded file is available to the agent.

## Run the sample

Configure the common declarative workflow settings described in the parent [README](../README.md), then run:

```pwsh
dotnet run
```

The sample always uploads `ProductBrief.txt` from this project. The program creates a `ChatMessage` whose content includes the prompt and uploaded file reference, then starts the workflow with that message. The YAML invokes the agent with `conversationId: =System.ConversationId` so the agent sees the same conversation item that contains the file.

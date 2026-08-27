# Declarative workflow file input

This sample demonstrates how to provide file-based input to a declarative workflow. It reads the bundled `ProductBrief.txt` file and creates a `ChatMessage` with the file content before starting a YAML-defined workflow.

The workflow displays `System.LastMessage.Text`, then invokes a Foundry-backed agent in the same workflow conversation.

## Run the sample

Configure the common declarative workflow settings described in the parent [README](../README.md), then run:

```pwsh
dotnet run
```

The sample always uses `ProductBrief.txt` from this project. Its contents are included in the workflow's input message. The YAML invokes the agent with `conversationId: =System.ConversationId` so the agent sees the same conversation item.

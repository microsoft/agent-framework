# Declarative workflow file input

This sample demonstrates how to provide file-based input to a declarative workflow. It converts a local file into a `ChatMessage` with both `TextContent` and `DataContent`, then starts a YAML-defined workflow with that message.

The workflow captures `System.LastMessage`, displays the message text and content count, and forwards the complete message to a Foundry-backed agent.

## Run the sample

Configure the common declarative workflow settings described in the parent [README](../README.md), then run:

```pwsh
dotnet run
```

By default the sample uses `ProductBrief.txt` from this project. To provide a different file and prompt:

```pwsh
dotnet run "C:\path\to\document.pdf" "Summarize this document for an executive audience."
```

The important part is that the file is not passed as plain text. The program creates a `ChatMessage` whose content includes the prompt and the file bytes, so the declarative workflow can access the input through `System.LastMessage` and pass the same message to downstream actions.

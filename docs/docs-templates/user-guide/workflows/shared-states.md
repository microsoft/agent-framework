# Microsoft Agent Framework Workflows: Shared States

This document provides an overview of **Shared States** in the Microsoft Agent Framework Workflow system.

## Overview

Shared States allow multiple executors within a workflow to access and modify common data. This feature is essential for scenarios where different parts of the workflow need to share information where direct message passing is not feasible or efficient.

## Writing to Shared States

::: zone pivot="programming-language-csharp"

```csharp
internal sealed class FileReadExecutor() : ReflectingExecutor<FileReadExecutor>("FileReadExecutor"), IMessageHandler<string, string>
{
    /// <summary>
    /// Reads a file and stores its content in a shared state.
    /// </summary>
    /// <param name="message">The path to the embedded resource file.</param>
    /// <param name="context">The workflow context for accessing shared states.</param>
    /// <returns>The ID of the shared state where the file content is stored.</returns>
    public async ValueTask<string> HandleAsync(string message, IWorkflowContext context)
    {
        // Read file content from embedded resource
        string fileContent = File.ReadAllText(message);
        // Store file content in a shared state for access by other executors
        string fileID = Guid.NewGuid().ToString();
        await context.QueueStateUpdateAsync<string>(fileID, fileContent, scopeName: "FileContent");

        return fileID;
    }
}
```

:::

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Accessing Shared States

::: zone pivot="programming-language-csharp"

```csharp
internal sealed class WordCountingExecutor() : ReflectingExecutor<WordCountingExecutor>("WordCountingExecutor"), IMessageHandler<string, int>
{
    /// <summary>
    /// Counts the number of words in the file content stored in a shared state.
    /// </summary>
    /// <param name="message">The ID of the shared state containing the file content.</param>
    /// <param name="context">The workflow context for accessing shared states.</param>
    /// <returns>The number of words in the file content.</returns>
    public async ValueTask<int> HandleAsync(string message, IWorkflowContext context)
    {
        // Retrieve the file content from the shared state
        var fileContent = await context.ReadStateAsync<string>(message, scopeName: "FileContent")
            ?? throw new InvalidOperationException("File content state not found");

        return fileContent.Split([' ', '\n', '\r'], StringSplitOptions.RemoveEmptyEntries).Length;
    }
}
```

::: zone-end

::: zone pivot="programming-language-python"

Coming soon...

::: zone-end

## Next Steps

- [Learn how to use agents in workflows](./using-agents.md) to build intelligent workflows.
- [Learn how to use workflows as agents](./as-agents.md).
- [Learn how to handle requests and responses](./request-and-response.md) in workflows.
- [Learn how to create checkpoints and resume from them](./checkpointing.md).

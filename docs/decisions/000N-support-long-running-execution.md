---
status: proposed
contact: semenshi
date: 2025-07-30
deciders: markwallace, rbarreto, dmytrostruk, westey-m, stephentoub, petchang
informed: {}
---

## Long-Running Execution Design

## Context and Problem Statement

The Agent Framework currently supports synchronous request-response patterns for AI agent interactions, 
where agents process requests and return results immediately. Similarly, MEAI chat clients follow the same 
synchronous pattern for AI interactions. However, many real-world AI scenarios involve complex tasks that 
require significant processing time, such as:
- Code generation and analysis tasks
- Complex reasoning and research operations  
- Image and content generation
- Large document processing and summarization

The current Agent Framework architecture needs to have native support for long-running execution patterns, as it 
The current Agent Framework architecture lacks native support for long-running execution patterns, which is 
essential for handling these scenarios effectively. Additionally, as MEAI chat clients may start supporting 
long-running execution capabilities in the future, the design should consider integration patterns and consistency 
with the broader Microsoft.Extensions.AI ecosystem to provide a unified experience across both agent and chat client scenarios.

## Decision Drivers
- Chat clients and agents should support long-running execution as well as quick prompts.
- The design should be simple and intuitive for developers to use.
- The design should be extensible to allow new long-running execution features to be added in the future.
- The design should be additive rather than disruptive to allow existing chat clients to iteratively add 
support for long-running executions without breaking existing functionality.

## APIs of Agents Supporting Long-Running Execution
<details>
<summary>OpenAI Responses</summary>

- Create a background response and wait for it to complete using polling:
    ```csharp
    ClientResult<OpenAI.Responses.OpenAIResponse> result = await this._openAIResponseClient.CreateResponseAsync("What is SLM in AI?", new ResponseCreationOptions
    {
        Background = true,
    });

    // InProgress, Completed, Cancelled, Queued, Incomplete, Failed
    while (result.Value.Status is (ResponseStatus.Queued or ResponseStatus.InProgress))
    {
        Thread.Sleep(500); // Wait for 0.5 seconds before checking the status again
        result = await this._openAIResponseClient.GetResponseAsync(result.Value.Id);
    }

    Console.WriteLine($"Response Status: {result.Value.Status}"); // Completed
    Console.WriteLine(result.Value.GetOutputText()); // SLM in the context of AI refers to ...
    ```

- Cancel a background response:
    ```csharp
    ...
    ClientResult<OpenAI.Responses.OpenAIResponse> result = await this._openAIResponseClient.CreateResponseAsync("What is SLM in AI?", new ResponseCreationOptions
    {
        Background = true,
    });

    result = await this._openAIResponseClient.CancelResponseAsync(result.Value.Id);

    Console.WriteLine($"Response Status: {result.Value.Status}"); // Cancelled
    ```

- Delete a background response:
    ```csharp
    ClientResult<OpenAI.Responses.OpenAIResponse> result = await this._openAIResponseClient.CreateResponseAsync("What is SLM in AI?", new ResponseCreationOptions
    {
        Background = true,
    });

    ClientResult<OpenAI.Responses.ResponseDeletionResult> deleteResult = await this._openAIResponseClient.DeleteResponseAsync(result.Value.Id);

    Console.WriteLine($"Response Deleted: {deleteResult.Value.Deleted}"); // True if the response was deleted successfully
    ```

- Streaming a background response
    ```csharp
    await foreach (StreamingResponseUpdate update in this._openAIResponseClient.CreateResponseStreamingAsync("What is SLM in AI?", new ResponseCreationOptions { Background = true }))
    {
        Console.WriteLine($"Sequence Number: {update.SequenceNumber}"); // 0, 1, 2, etc.

        switch (update)
        {
            case StreamingResponseCreatedUpdate createdUpdate:
                Console.WriteLine($"Response Status: {createdUpdate.Response.Status}"); // Queued
                break;
            case StreamingResponseQueuedUpdate queuedUpdate:
                Console.WriteLine($"Response Status: {queuedUpdate.Response.Status}"); // Queued
                break;
            case StreamingResponseInProgressUpdate inProgressUpdate:
                Console.WriteLine($"Response Status: {inProgressUpdate.Response.Status}"); // InProgress
                break;
            case StreamingResponseOutputItemAddedUpdate outputItemAddedUpdate:
                Console.WriteLine($"Output index: {outputItemAddedUpdate.OutputIndex}");
                Console.WriteLine($"Item Id: {outputItemAddedUpdate.Item.Id}");
                break;
            case StreamingResponseContentPartAddedUpdate contentPartAddedUpdate:
                Console.WriteLine($"Output Index: {contentPartAddedUpdate.OutputIndex}");
                Console.WriteLine($"Item Id: {contentPartAddedUpdate.ItemId}");
                Console.WriteLine($"Content Index: {contentPartAddedUpdate.ContentIndex}");
                break;
            case StreamingResponseOutputTextDeltaUpdate outputTextDeltaUpdate:
                Console.WriteLine($"Output Index: {outputTextDeltaUpdate.OutputIndex}");
                Console.WriteLine($"Item Id: {outputTextDeltaUpdate.ItemId}");
                Console.WriteLine($"Content Index: {outputTextDeltaUpdate.ContentIndex}");
                Console.WriteLine($"Delta: {outputTextDeltaUpdate.Delta}");  // SL>M> in> AI> typically>....
                break;
            case StreamingResponseOutputTextDoneUpdate outputTextDoneUpdate:
                Console.WriteLine($"Output Index: {outputTextDoneUpdate.OutputIndex}");
                Console.WriteLine($"Item Id: {outputTextDoneUpdate.ItemId}");
                Console.WriteLine($"Content Index: {outputTextDoneUpdate.ContentIndex}");
                Console.WriteLine($"Text: {outputTextDoneUpdate.Text}");  // SLM in the context of AI typically refers to ...
                break;
            case StreamingResponseContentPartDoneUpdate contentPartDoneUpdate:
                Console.WriteLine($"Output Index: {contentPartDoneUpdate.OutputIndex}");
                Console.WriteLine($"Item Id: {contentPartDoneUpdate.ItemId}");
                Console.WriteLine($"Content Index: {contentPartDoneUpdate.ContentIndex}");
                Console.WriteLine($"Text: {contentPartDoneUpdate.Part.Text}");  // SLM in the context of AI typically refers to ...
                break;
            case StreamingResponseOutputItemDoneUpdate outputItemDoneUpdate:
                Console.WriteLine($"Output Index: {outputItemDoneUpdate.OutputIndex}");
                Console.WriteLine($"Item Id: {outputItemDoneUpdate.Item.Id}");
                break;
            case StreamingResponseCompletedUpdate completedUpdate:
                Console.WriteLine($"Response Status: {completedUpdate.Response.Status}"); // Completed
                Console.WriteLine($"Output: {completedUpdate.Response.GetOutputText()}"); // SLM in the context of AI typically refers to ...
                break;
            default:
                Console.WriteLine($"Unexpected update type: {update.GetType().Name}");
                break;
        }
    }
    ```
Docs: [OpenAI background mode](https://platform.openai.com/docs/guides/background)
</details>

<details>
<summary>Azure AI Foundry Agents</summary>

- Create a thread and run the agent against it and wait for it to complete using polling:
    ```csharp
    // Create a thread with a message.
    ThreadMessageOptions options = new(MessageRole.User, "What is SLM in AI?");
    thread = await this._persistentAgentsClient!.Threads.CreateThreadAsync([options]);

    // Run the agent on the thread.
    ThreadRun threadRun = await this._persistentAgentsClient.Runs.CreateRunAsync(thread.Id, agent.Id);

    // Poll for the run status.
    // InProgress, Completed, Cancelling, Cancelled, Queued, Failed, RequiresAction, Expired
    while (threadRun.Status == RunStatus.InProgress || threadRun.Status == RunStatus.Queued)
    {
        threadRun = await this._persistentAgentsClient.Runs.GetRunAsync(thread.Id, threadRun.Id);
    }

    // Access the run result.
    await foreach (PersistentThreadMessage msg in this._persistentAgentsClient.Messages.GetMessagesAsync(thread.Id, threadRun.Id))
    {
        foreach (MessageContent content in msg.ContentItems)
        {
            switch (content)
            {
                case MessageTextContent textItem:
                    Console.WriteLine($"  Text: {textItem.Text}");
                    //M1: In the context of Artificial Intelligence (AI), **SLM** often ...
                    //M2: What is SLM in AI?
                    break;
            }
        }
    }
    ```

- Cancel an agent run:
    ```csharp
    // Create a thread with a message.
    ThreadMessageOptions options = new(MessageRole.User, "What is SLM in AI?");
    thread = await this._persistentAgentsClient!.Threads.CreateThreadAsync([options]);

    // Run the agent on the thread.
    ThreadRun threadRun = await this._persistentAgentsClient.Runs.CreateRunAsync(thread.Id, agent.Id);

    Response<ThreadRun> cancellationResponse = await this._persistentAgentsClient.Runs.CancelRunAsync(thread.Id, threadRun.Id);
    ```

- Other agent run operations:
    GetRunStepAsync, UpdateRunAsync

</details>

<details>
<summary>A2A Agents</summary>

- Send message to agent and handle the response
    ```csharp
    // Send message to the A2A agent.
    A2AResponse response = await this.Client.SendMessageAsync(messageSendParams, cancellationToken).ConfigureAwait(false);

    // Handle task responses.
    if (response is AgentTask task)
    {
        while (task.Status.State == TaskState.Working)
        {
            task = await this.Client.GetTaskAsync(task.Id, cancellationToken).ConfigureAwait(false);
        }

        if (task.Artifacts != null && task.Artifacts.Count > 0)
        {
            foreach (var artifact in task.Artifacts)
            {
                foreach (var part in artifact.Parts)
                {
                    if (part is TextPart textPart)
                    {
                        Console.WriteLine($"Result: {textPart.Text}");
                    }
                }
            }
            Console.WriteLine();
        }
    }
    // Handle message responses.
    else if (response is Message message)
    {
        foreach (var part in message.Parts)
        {
            if (part is TextPart textPart)
            {
                Console.WriteLine($"Result: {textPart.Text}");
            }
        }
    }
    else
    {
        throw new InvalidOperationException("Unexpected response type from A2A client.");
    }
    ```

- Cancel task
    ```csharp
    // Send message to the A2A agent.
    A2AResponse response = await this.Client.SendMessageAsync(messageSendParams, cancellationToken).ConfigureAwait(false);

    // Cancel the task
    if (response is AgentTask task)
    {
        await this.Client.CancelTaskAsync(new TaskIdParams() { Id = task.Id }, cancellationToken).ConfigureAwait(false);
    }
    ```

</details>

## Comparison of Long-Running Execution Features
|        Feature              | OpenAI Responses          | Foundry Agents                      | A2A                  |
|-----------------------------|---------------------------|-------------------------------------|----------------------|
| Initiated by                | User (Background = true)  | Long-running execution is always on | Agent                |
| Modeled as 			      | Response                  | Run                                 | Task                 |
| Supported modes<sup>1</sup> | Sync, Async               | Async                               | Sync, Async          |
| Getting status support      | ✅                        | ✅                                 | ✅                   |
| Getting result support      | ✅                        | ✅                                 | ✅                   |
| Update support              | ❌                        | ✅                                 | ✅                   |
| Cancellation support        | ✅                        | ✅                                 | ✅                   |
| Delete support              | ✅                        | ❌                                 | ❌                   |
| Non-streaming support       | ✅                        | ✅                                 | ✅                   |
| Streaming support           | ✅                        | ✅                                 | ✅                   |
| Execution statuses          | InProgress, Completed, Queued <br/>Cancelled, Failed, Incomplete | InProgress, Completed, Queued<br/>Cancelled, Failed, Cancelling, <br/>RequiresAction, Expired |  Working, Completed, Canceled, <br/>Failed, Rejected, AuthRequired, <br/>InputRequired, Submitted, Unknown |

<sup>1</sup> Sync is a regular message-based request/response communication pattern, Async is a pattern for long-running tasks where the agent returns an Id for a run/task and allows polling for status and final results by the Id.

**Note:** The names for new classes, interfaces, and their members used in the sections below are tentative and will be discussed in a dedicated section of this document.

## Long-Running Execution Support for Chat Clients

This section describes different options for adding long-running execution support to chat clients that implement the `IChatClient` interface.

### 1. Methods for Working with Long-Running Executions

Based on the analysis of existing APIs that support long-running executions (such as OpenAI Responses, Azure AI Foundry Agents, and A2A), 
the following operations are used for working with long-running executions:
- Common operations:
  - **Start Long-Running Execution**: Initiates a long-running execution and returns an Id of the execution.
  - **Get Status of Long-Running Execution**: This method is used to retrieve the status of a long-running execution.
  - **Get Result of Long-Running Execution**: Retrieves the result of a long-running execution.
- Uncommon operations:
  - **Update Long-Running Execution**: This method is used to update a long-running execution, such as adding new messages or modifying existing ones.
  - **Cancel Long-Running Execution**: This method is used to cancel a long-running execution that is still in progress.
  - **Delete Long-Running Execution**: This method is used to delete a long-running execution, typically after it has completed or been cancelled.

To support these operations by `IChatClient` implementations, the following options are available:
- **1.1 New IAsyncChatClient Interface For All Long-Running Execution Operations**
- **1.2 New IAsyncChatClient Interface For Uncommon Operations + Use Get{Streaming}ResponseAsync For Common Operations**
- **1.3 New IAsyncChatClient Interface For Uncommon Operations + Use Get{Streaming}ResponseAsync For Common Operations + Capability Check**
- **1.4 Individual Interface Per Uncommon Operation + Use Get{Streaming}ResponseAsync For Common Operations**

#### 1.1 New IAsyncChatClient Interface For All Long-Running Execution Operations

This option suggests adding a new interface `IAsyncChatClient` that some implementations of `IChatClient` may implement to support long-running executions.
```csharp
public interface IAsyncChatClient
{
    Task<AsyncRunResult> StartAsyncRunAsync(IList<ChatMessage> chatMessages, RunOptions? options = null, CancellationToken ct = default);
    Task<AsyncRunResult> GetAsyncRunStatusAsync(string runId, CancellationToken ct = default);
    Task<AsyncRunResult> GetAsyncRunResultAsync(string runId, CancellationToken ct = default);
    Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken ct = default);
    Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken ct = default);
    Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken ct = default);
}

public class CustomChatClient : IChatClient, IAsyncChatClient
{
    ...
}
```

Consumer code example:
```csharp
IChatClient chatClient = new CustomChatClient();

string prompt = "..."

// Determine if the prompt should be run as a long-running execution
if(chatClient.GetService<IAsyncChatClient>() is { } asyncChatClient && ShouldRunPromptAsynchronously(prompt)) 
{
    try
    {
        // Start a long-running execution
        AsyncRunResult result = await asyncChatClient.StartAsyncRunAsync(prompt);
    }
    catch (NotSupportedException)
    {
        Console.WriteLine("This chat client does not support long-running executions.");
        throw;
    }

    AsyncRunContent? asyncRunContent = GetAsyncRunContent(result);
    
    // Poll for the status of the long-running execution
    while (asyncRunContent.Status is AsyncRunStatus.InProgress or AsyncRunStatus.Queued)
    {
        result = await asyncChatClient.GetAsyncRunStatusAsync(asyncRunContent.RunId);
        asyncRunContent = GetAsyncRunContent(result);
    }
    
    // Get the result of the long-running execution
    result = await asyncChatClient.GetAsyncRunResultAsync(result.RunId);
    Console.WriteLine(result);
}
else
{
    // Complete a quick prompt
    ChatResponse response = await chatClient.GetResponseAsync(prompt);
    Console.WriteLine(response);
}
```

**Pros:**
- Not a breaking change: Existing chat clients are not affected.
- Callers can determine if a chat client supports long-running executions by calling its `GetService<IAsyncChatClient>()` method.

**Cons:**
- Not extensible: Adding new methods to the `IAsyncChatClient` interface after its release will break existing implementations of the interface.
- Missing capability check: Callers cannot determine if chat clients support specific uncommon operations before attempting to use them.
- Insufficient information: Callers may not have enough information to decide whether a prompt should run as a long-running execution.
- The new methods calls bypass existing decorators such as logging, telemetry, etc.

#### 1.2 New IAsyncChatClient Interface For Uncommon Operations + Use Get{Streaming}ResponseAsync For Common Operations

This option suggests using the existing `GetResponseAsync` and `GetStreamingResponseAsync` methods of the `IChatClient` interface to support 
common long-running execution operations, such as starting long-running executions, getting their status, their results, and potentially 
updating them, in addition to their existing functionality of serving quick prompts. Methods for the uncommon operations, such as updating, 
cancelling, and deleting long-running executions, will be added to a new `IAsyncChatClient` interface that will be implemented by chat clients 
that support them.

This option presumes that Option 3.2 (Have one method for getting long-running execution status and result) is selected.

```csharp
public interface IAsyncChatClient
{
    /// The update can be handled by GetResponseAsync method as well.
    Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken ct = default);
    
    Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken ct = default);
    Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken ct = default);
}

public class ResponsesChatClient : IChatClient, IAsyncChatClient
{
    public async Task<ChatResponse> GetResponseAsync(string prompt, ChatOptions? options = null, CancellationToken ct = default)
    {
        ClientResult<OpenAI.Responses.OpenAIResponse>? result = null;

        // If long-running execution mode is enabled, we run the prompt as a long-running execution
        if(runAsynchronously)
        {
            // No RunId is provided, so we start a long-running execution
            if(options?.RunId is null)
            {
                result = await this._openAIResponseClient.CreateResponseAsync(prompt, new ResponseCreationOptions
                {
                    Background = true,
                });
            }
            else // RunId is provided, so we get the status of a long-running execution
            {
                result = await this._openAIResponseClient.GetResponseAsync(options.RunId);
            }
        }
        else
        {
            // Handle the case when the prompt should be run as a quick prompt
            result = await this._openAIResponseClient.CreateResponseAsync(prompt, new ResponseCreationOptions
            {
                Background = false
            });
        }

        ...
    }

    public Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken ct = default)
    {
        throw new NotSupportedException("This chat client does not support updating long-running executions.");
    }

    public Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken cancellationToken = default)
    {
        return this._openAIResponseClient.CancelResponseAsync(runId, cancellationToken);
    }

    public Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken cancellationToken = default)
    {
        return this._openAIResponseClient.DeleteResponseAsync(runId, cancellationToken);
    }
}
```

Consumer code example:
```csharp
IChatClient chatClient = new ResponsesChatClient();

ChatResponse response = await chatClient.GetResponseAsync("<prompt>");

if (GetAsyncRunContent(response) is AsyncRunContent asyncRunContent)
{
    // Get result of the long-running execution
    response = await chatClient.GetAsyncRunResultAsync([], new ChatOptions
    { 
        RunId = asyncRunContent.RunId 
    });

    // After some time

    // If it's still running, cancel and delete the run
    if (GetAsyncRunContent(response).Status is AsyncRunStatus.InProgress or AsyncRunStatus.Queued)
    {
        IAsyncChatClient? asyncChatClient = chatClient.GetService<IAsyncChatClient>();

        try
        {
            await asyncChatClient?.CancelAsyncRunAsync(asyncRunContent.RunId);
        }
        catch (NotSupportedException)
        {
            Console.WriteLine("This chat client does not support cancelling long-running executions.");
        }
        
        try
        {
            await asyncChatClient?.DeleteAsyncRunAsync(asyncRunContent.RunId);
        }
        catch (NotSupportedException)
        {
            Console.WriteLine("This chat client does not support deleting long-running executions.");
        }
    }
}
else
{
    // Handle the case when the response is a quick prompt completion
    Console.WriteLine(response);
}
```

This option addresses the issue that the other options above have with callers needing to know whether the prompt should 
be run as a long-running execution or a quick prompt. It allows callers to simply call the existing `GetResponseAsync` method, 
and the chat client will decide whether to run the prompt as a long-running execution or a quick prompt. If control over 
the execution mode is still needed, and the underlying API supports it, it will be possible for callers to set the mode via
the chat client invocation or configuration. More details about this are provided in one of the sections below about enabling long-running execution mode.
  
Additionally, it addresses another issue with the other options above, where the `GetResponseAsync` method may return a long-running
execution response and the `StartAsyncRunAsync` method may return a quick prompt response. Having one method that handles both cases
allows callers to not worry about this behavior and simply check the type of the response to determine if it is a long-running execution
or a quick prompt completion.

With the `GetResponseAsync` method becoming responsible for starting, getting status, getting results and updating long-running executions,
there are only a few operations left in the `IAsyncChatClient` interface - cancel and delete. As a result, the `IAsyncChatClient` interface
name may not be the best fit, as it suggests that it is responsible for all long-running execution operations while it is not. Should 
the interface be renamed to reflect operations it supports? What should the new name be? Probably not. Option 1.4 considers an alternative
that might solve the naming issue. 

**Pros:**
- Delegation and control: Callers delegate the decision of whether to run a prompt as a long-running execution or quick prompt to the chat client, 
while still having the option to control the execution mode to determine how to handle the prompt if needed.
- Not a breaking change: Existing chat clients are not affected. 
  
**Cons:**  
- Not extensible: Adding new methods to the `IAsyncChatClient` interface after its release will break existing implementations of the interface. 
- Calls to the new methods bypass existing decorators such as logging, telemetry, etc.
- Missing capability check: Callers cannot determine if chat clients support specific uncommon operations before attempting to use them.

#### 1.3 New IAsyncChatClient Interface For Uncommon Operations + Use Get{Streaming}ResponseAsync For Common Operations + Capability Check

This option extends the previous option with a way for callers to determine if a chat client supports uncommon operations before attempting to use them.

```csharp
public interface IAsyncChatClient
{
    bool CanUpdateAsyncRun { get; }
    bool CanCancelAsyncRun { get; }  
    bool CanDeleteAsyncRun { get; } 

    Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken ct = default);
    Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken ct = default);
    Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken ct = default);
}

public class ResponsesChatClient : IChatClient, IAsyncChatClient
{
    public async Task<ChatResponse> GetResponseAsync(string prompt, ChatOptions? options = null, CancellationToken ct = default)
    {
        ...
    }

    public bool CanUpdateAsyncRun => false; // This chat client does not support updating long-running executions.
    public bool CanCancelAsyncRun => true;  // This chat client supports cancelling long-running executions.
    public bool CanDeleteAsyncRun => true;  // This chat client supports deleting long-running executions.

    public Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken ct = default)
    {
        throw new NotSupportedException("This chat client does not support updating long-running executions.");
    }

    public Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken cancellationToken = default)
    {
        return this._openAIResponseClient.CancelResponseAsync(runId, cancellationToken);
    }

    public Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken cancellationToken = default)
    {
        return this._openAIResponseClient.DeleteResponseAsync(runId, cancellationToken);
    }
}
```

Consumer code example:
```csharp
IChatClient chatClient = new ResponsesChatClient();

ChatResponse response = await chatClient.GetResponseAsync("<prompt>");

if (GetAsyncRunContent(response) is AsyncRunContent asyncRunContent)
{
    // Get result of the long-running execution
    response = await chatClient.GetAsyncRunResultAsync([], new ChatOptions
    { 
        RunId = asyncRunContent.RunId 
    });

    // After some time

    IAsyncChatClient? asyncChatClient = chatClient.GetService<IAsyncChatClient>();

    // If it's still running, cancel and delete the run
    if (GetAsyncRunContent(response).Status is AsyncRunStatus.InProgress or AsyncRunStatus.Queued)
    {
        if(asyncChatClient?.CanCancelAsyncRun ?? false)
        {
            await asyncChatClient?.CancelAsyncRunAsync(asyncRunContent.RunId);
        }

        if(asyncChatClient?.CanDeleteAsyncRun ?? false)
        {
            await asyncChatClient?.DeleteAsyncRunAsync(asyncRunContent.RunId);
        }       
    }
}
else
{
    // Handle the case when the response is a quick prompt completion
    Console.WriteLine(response);
}
```

**Pros:**
- Delegation and control: Callers delegate the decision of whether to run a prompt as a long-running execution or quick prompt to the chat client, 
while still having the option to control the execution mode to determine how to handle the prompt if needed.
- Not a breaking change: Existing chat clients are not affected. 
- Capability check: Callers can determine if the chat client supports an uncommon operation before attempting to use it.
  
**Cons:**  
- Not extensible: Adding new members to the `IAsyncChatClient` interface after its release will break existing implementations of the interface.  
- Calls to the new methods bypass existing decorators such as logging, telemetry, etc.

#### 1.4 Individual Interface Per Uncommon Operation + Use Get{Streaming}ResponseAsync For Common Operations

This option suggests using the existing `GetResponseAsync` and `GetStreamingResponseAsync` methods of the `IChatClient` interface to support 
common long-running execution operations, such as starting long-running executions, getting their status, and their results, in addition to 
their existing functionality of serving quick prompts.

The uncommon operations that are not supported by all analyzed APIs, such as updating (which can be handled by `Get{Streaming}ResponseAsync`), cancelling, 
and deleting long-running executions, as well as future ones will be added to their own interfaces that will be implemented by chat clients 
that support them.

This option presumes that Option 3.2 (Have one method for getting long-running execution status and result) is selected.

```csharp
public interface ICancelableAsyncRun
{  
    Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken cancellationToken = default);
}

public interface IUpdatableAsyncRun
{  
    Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken cancellationToken = default);
}

public interface IDeletableAsyncRun
{  
    Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken cancellationToken = default);
}

// Responses chat client that supports standard long-running execution operations + cancellation and deletion
public class ResponsesChatClient : IChatClient, ICancelableAsyncRun, IDeletableAsyncRun
{
    public async Task<ChatResponse> GetResponseAsync(string prompt, ChatOptions? options = null, CancellationToken ct = default)
    {
        ...
    }

    public Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken cancellationToken = default)
    {
        return this._openAIResponseClient.CancelResponseAsync(runId, cancellationToken);
    }

    public Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken cancellationToken = default)
    {
        return this._openAIResponseClient.DeleteResponseAsync(runId, cancellationToken);
    }
}
```

Example that starts a long-running execution, gets its status, and cancels and deletes it if it's not completed after some time:
```csharp
IChatClient chatClient = new ResponsesChatClient();

ChatResponse response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AsynchronousRun = true });

if (GetAsyncRunContent(response) is AsyncRunContent asyncRunContent)
{
    // Attempt to get result
    response = await chatClient.GetAsyncRunResultAsync([], new ChatOptions
    { 
        RunId = asyncRunContent.RunId 
    });

    // After some time

    // If it's still running, cancel and delete the run
    if (GetAsyncRunContent(response).Status is AsyncRunStatus.InProgress or AsyncRunStatus.Queued)
    {
        if(chatClient.GetService<ICancelableAsyncRun>() is {} cancelableAsyncRun)
        {
            await cancelableAsyncRun.CancelAsyncRunAsync(asyncRunContent.RunId);
        }
        
        if(chatClient.GetService<IDeletableAsyncRun>() is {} deletableAsyncRun)
        {
            await deletableAsyncRun.DeleteAsyncRunAsync(asyncRunContent.RunId);
        }
    }
}
```

**Pros:**
- Extensible: New interfaces can be added and implemented to support new long-running execution operations without breaking 
existing chat client implementations.
- Not a breaking change: Existing chat clients that implement the `IChatClient` interface are not affected.
- Delegation and control: Callers delegate the decision of whether to run a prompt as a long-running execution or quick prompt
to the chat client, while still having the option to control the execution mode to determine how to handle the prompt if needed.
  
**Cons:**  
- Breaking changes: Changing the signatures of the methods of the operation-specific interfaces or adding new members to them will 
break existing implementations of those interfaces. However, the blast radius of this change is much smaller and limited to a subset
of chat clients that implement the operation-specific interfaces. However, this is still a breaking change.

### 2. Enabling Long-Running Execution

Based on the API analysis, some APIs must be explicitly configured to run in long-running execution mode, 
while others don't need additional configuration because they either decide themselves whether a request
should run as a long-running execution, or they always operate in long-running execution mode or quick prompt mode:
|        Feature              | OpenAI Responses          | Foundry Agents                      | A2A                  |
|-----------------------------|---------------------------|-------------------------------------|----------------------|
| Long-running execution      | User (Background = true)  | Long-running execution is always on | Agent                |


The options below consider how to specify the long-running execution mode for chat clients that support both quick prompts and long-running executions.

#### Option 2.1 Specify Execution Mode per `Get{Streaming}ResponseAsync` Method Invocation

This option proposes adding a new nullable `AsynchronousRun` property to the `ChatOptions` type that represents options
for the `Get{Streaming}ResponseAsync` methods. The property value will be `true` if the caller requests a long-running execution, `false` otherwise.
  
Chat clients that work with APIs requiring explicit configuration per operation will use this property to determine whether to run the prompt as a long-running 
execution or quick prompt. Chat clients that work with APIs that don't require explicit configuration will ignore this property and operate according 
to their own logic/configuration.

```csharp
public class ChatOptions
{
    // Existing properties...
    public bool? AsynchronousRun { get; set; }
}

// Consumer code example
IChatClient chatClient = ...; // Get an instance of IChatClient

// Start a long-running execution for the prompt
ChatResponse response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AsynchronousRun = true });

// Start a quick prompt
ChatResponse quickResponse = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AsynchronousRun = false });
```

**Pros:** Callers can switch between quick prompts and long-running executions per invocation of the `Get{Streaming}ResponseAsync` methods without changing the client configuration.

**Cons:** This may not be valuable for all callers, as they may not have enough information to decide whether the prompt should run as a long-running execution or quick prompt.

#### Option 2.2 Specify Execution Mode per Chat Client Instance

This option proposes adding a new `asynchronousRun` parameter to constructors of chat clients that support both quick prompts and long-running executions.
The parameter value will be `true` if the chat client should operate in long-running execution mode, `false` otherwise.

Chat clients that work with APIs requiring explicit configuration will use this parameter to determine whether to run prompts as long-running executions or quick prompts.
Chat clients that work with APIs that don't require explicit configuration won't have this parameter in their constructors and will operate according to their own logic/configuration.

```csharp

public class CustomChatClient : IChatClient, IAsyncChatClient
{
    private readonly bool _asynchronousRun;

    public CustomChatClient(bool asynchronousRun)
    {
        this._asynchronousRun = asynchronousRun;
    }

    // Existing methods...
}

// Consumer code example
IChatClient chatClient = new CustomChatClient(asynchronousRun: true);

// Start a long-running execution for the prompt
ChatResponse response = await chatClient.GetResponseAsync("<prompt>");
```

Chat clients can be configured to always operate in long-running execution mode or quick prompt mode based on their role in a specific scenario.
For example, a chat client responsible for generating ideas for images can be configured for quick prompt mode, while a chat client responsible for image 
generation can be configured to always use long-running execution mode.

**Pros:** Can be beneficial for scenarios where the chat clients need to be configured upfront in accordance with their role in a scenario.

**Cons:** Less flexible than the previous option, as it requires changing the chat client configuration to switch between quick prompts and long-running executions.
However, this flexibility might not be needed.

#### Option 2.3 Combined Approach

This option proposes a combined approach that allows configuration per chat client instance and per `Get{Streaming}ResponseAsync` method invocation.

The chat client will use whichever configuration is provided, whether set in the chat client constructor or in the options for the `Get{Streaming}ResponseAsync` 
method invocation. If both are set, the one provided in the `Get{Streaming}ResponseAsync` method invocation takes precedence.

```csharp
public class CustomChatClient : IChatClient, IAsyncChatClient
{
    private readonly bool _asynchronousRun;
    public CustomChatClient(bool asynchronousRun)
    {
        this._asynchronousRun = asynchronousRun;
    }
    
    public async Task<ChatResponse> GetResponseAsync(string prompt, ChatOptions? options = null, CancellationToken ct = default)
    {
        bool runAsynchronously = options?.AsynchronousRun ?? this._asynchronousRun;
        // Logic to handle the prompt based on runAsynchronously...
    }
}

// Consumer code example
IChatClient chatClient = new CustomChatClient(asynchronousRun: true);

// Start a long-running execution for the prompt
ChatResponse response = await chatClient.GetResponseAsync("<prompt>");

// Start a quick prompt
ChatResponse quickResponse = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AsynchronousRun = false });
```

**Pros:** Flexible approach that combines the benefits of both previous options.

### 3. Getting Status and Result of Long-Running Execution

The explored APIs use different approaches for retrieving the status and results of long-running executions. Some are using
one method to retrieve both status and result, while others use two separate methods for each operation:
|        Feature    | OpenAI Responses              | Foundry Agents                                     | A2A                   |
|-------------------|-------------------------------|----------------------------------------------------|-----------------------|
| API to Get Status | GetResponseAsync(responseId)  | Runs.GetRunAsync(thread.Id, threadRun.Id)          | GetTaskAsync(task.Id) |
| API to Get Result | GetResponseAsync(responseId)  | Messages.GetMessagesAsync(thread.Id, threadRun.Id) | GetTaskAsync(task.Id) |

Taking into account the differences, the following options propose a few ways to model the API for getting the status and result of 
long-running executions for the `AIAgent` interface implementations.

#### Option 3.1: Two Separate Methods for Status and Result

This option suggests having two separate methods for getting the status and result of long-running executions:
```csharp
public interface IAsyncChatClient
{
    Task<AsyncRunResult> GetAsyncRunStatusAsync(string runId, CancellationToken ct = default);
    Task<AsyncRunResult> GetAsyncRunResultAsync(string runId, CancellationToken ct = default);
}
```

**Pros:** Could be more intuitive for developers, as it clearly separates the concerns of checking the status and retrieving the result of a long-running execution.

**Cons:** Creates inefficiency for chat clients that use APIs that return both status and result in a single call, 
as callers might make redundant calls to get the result after checking the status that already contains the result.

#### Option 3.2: One Method to Get Status and Result

This option suggests having a single method for getting both the status and result of long-running executions:
```csharp
public interface IAsyncChatClient
{
    Task<AsyncRunResult> GetAsyncRunResultAsync(string runId, AgentThread? thread = null, CancellationToken ct = default);
}
```

This option will redirect the call to the one appropriate method of the underlying API that uses one method to retrieve both.
For APIs that use two separate methods, the method will first get the status and if the status indicates that the 
execution is still running, it will return the status to the caller. If the status indicates that the execution is completed,
it will then call the method to get the result of the long-running execution and return it together with the status.

**Pros:**
- Simplifies the API by providing a single, intuitive method for retrieving long-running execution information.
- More optimal for chat clients that use APIs that return both status and result in a single call, as it avoids unnecessary API calls.

## 4. Place For RunId, Status, and UpdateId of Long-Running Execution

This section considers different options for exposing the `RunId`, `Status`, and `UpdateId` properties of long-running executions.

### Option 4.1. As AIContent

The `AsyncRunContent` class will represent a long-running execution initiated and managed by an agent/LLM.
Items of this content type will be returned in a chat message as part of the `AgentRunResponse` or `ChatResponse`
response to represent the long-running execution.

The `AsyncRunContent` class has two properties: `RunId` and `Status`. The `RunId` identifies the 
long-running execution, and the `Status` represents the current status of the execution. The class  
inherits from `AIContent`, which is a base class for all AI-related content in MEAI and AF.

The `AsyncRunStatus` class represents the status of a long-running execution. Initially, it will have 
a set of predefined statuses that represent the possible statuses used by existing Agent/LLM APIs that support
long-running executions. It will be extended to support additional statuses as needed while also
allowing custom, not-yet-defined statuses to propagate as strings from the underlying API to the callers.

The content class type can be used by both agents and chat clients to represent long-running executions.
For chat clients to use it, it should be declared in one of the MEAI packages.

```csharp
public class AsyncRunContent : AIContent
{
    public string RunId { get; }
    public AsyncRunStatus? Status { get; }
}

public readonly struct AsyncRunStatus : IEquatable<AsyncRunStatus>
{
    public static AsyncRunStatus Queued { get; } = new("Queued");
    public static AsyncRunStatus InProgress { get; } = new("InProgress");
    public static AsyncRunStatus Completed { get; } = new("Completed");
    public static AsyncRunStatus Cancelled { get; } = new("Cancelled");
    public static AsyncRunStatus Failed { get; } = new("Failed");
    public static AsyncRunStatus RequiresAction { get; } = new("RequiresAction");
    public static AsyncRunStatus Expired { get; } = new("Expired");
    public static AsyncRunStatus Rejected { get; } = new("Rejected");
    public static AsyncRunStatus AuthRequired { get; } = new("AuthRequired");
    public static AsyncRunStatus InputRequired { get; } = new("InputRequired");
    public static AsyncRunStatus Unknown { get; } = new("Unknown");

    public string Label { get; }

    public AsyncRunStatus(string label)
    {
        if (string.IsNullOrWhiteSpace(label))
        {
            throw new ArgumentException("Label cannot be null or whitespace.", nameof(label));
        }

        this.Label = label;
    }

    /// Other members
}
````

The streaming API may return an UpdateId identifying a particular update within a streamed response. 
This UpdateId should be available together with RunId to callers, allowing them to resume a long-running execution identified 
by the RunId from the last received update, identified by the UpdateId.
TBD: Explore this further if the option is selected.

### Option 4.2. As Properties Of ChatResponse
TBD

## 5. Streaming Support
TBD
 
### Decision Outcome
TBD

## Proposed Design for Supporting Long-Running Executions by AF Agents

The design for supporting long-running executions by agents is very similar to that for chat clients because it is based on 
the same analysis of existing APIs and anticipated consumption patterns.

One difference, apart from names and signatures, is that the parent of all agents in AF is the `AIAgent` abstract class,
which is not as prone to breaking changes as the `IChatClient` interface is when new members are added to it. Therefore, 
the methods for working with long-running executions can be added to the `AIAgent` class as first-class citizens 
without worrying about breaking changes if the design decides to go with this option.

Having considered the pros and cons of all options for supporting long-running executions by chat clients, 
the draft design for supporting long-running executions by agents is as follows:
- All new methods for common and uncommon operations will be added to the `AIAgent` abstract class as virtual methods.
  - The methods will throw a `NotSupportedException` exception if an operation is not overridden by the agent implementation, which may happen
  if the agent does not support long-running executions at all or does not support the specific operation.
  - There will be one method for getting the status and result of a long-running execution, instead of two separate ones.
- The `Run{Streaming}Async` methods will be used to trigger long-running executions in addition to their existing functionality of running quick prompts.
  - They will return an `AsyncRunContent` item as part of the response if the prompt is run as a long-running execution.
  - They will return an item of `AIContent` type, like `TextContent`, as they do today if the prompt is run as a quick prompt.
- The `AIAgent` class will be extended with a mechanism to indicate supported capabilities of the agent, such as update, cancel, and delete long-running executions.
  - This will allow callers to check if the agent supports a specific operation before calling it.
- The `asynchronousRun` parameter will be added to the constructors of agents that support both quick prompts and long-running executions.
  - The parameter value will be `true` if the agent should operate in long-running execution mode, `false` otherwise.
- The `AgentRunOptions` class will be extended with a new `AsynchronousRun` property to allow enabling long-running execution mode per invocation of the `Run{Streaming}Async` methods.
  - If the property is set to `true`, and the agent supports long-running executions, then the prompt will be run as a long-running execution.
  - If the property is set to `false`, or the agent does not support long-running executions, then the prompt will be run as a quick prompt.
  - The property won't have any effect on agents that can decide themselves whether to run a prompt as a long-running execution or quick prompt.
  - The property will have precedence over the `asynchronousRun` parameter passed to the agent constructor.

**Note:** The exact implementation details can be explored further if this design is agreed on principle.

New API to support long-running executions by agents:

```csharp
public abstract class AIAgent
{
    // Existing methods
    public virtual Task<AgentRunResponse> RunAsync(string message, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken ct = default) {...}

    // New methods for long-running executions    
    public virtual Task<AgentRunResponse> GetAsyncRunResultAsync(string runId, AgentThread? thread = null, CancellationToken ct = default) {...};
    public virtual Task<AgentRunResponse> UpdateAsyncRunAsync(string runId, AgentThread? thread = null, IList<ChatMessage> chatMessages, CancellationToken ct = default) {...};
    public virtual Task<AgentRunResponse> CancelAsyncRunAsync(string runId, AgentThread? thread = null, CancellationToken ct = default) {...};
    public virtual Task<AgentRunResponse> DeleteAsyncRunAsync(string runId, AgentThread? thread = null, CancellationToken ct = default) {...};
    
    // New properties to indicate supported capabilities.
    public virtual bool CanUpdateAsyncRun => false;
    public virtual bool CanCancelAsyncRun => false;
    public virtual bool CanDeleteAsyncRun => false;
}

// Agent that support update and cancellation
public class CustomAgent : AIAgent
{
    private readonly bool _asynchronousRun;

    public CustomAgent(bool asynchronousRun)
    {
        this._asynchronousRun = asynchronousRun;
    }

    public override Task<AgentRunResponse> RunAsync(string message, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken ct = default)
    {
        var runAsynchronously = options?.AsynchronousRun ?? this._asynchronousRun;
        // Logic to run the prompt as a long-running execution or quick prompt...
    }

    public override Task<AgentRunResponse> GetAsyncRunResultAsync(string runId, AgentThread? thread = null, CancellationToken ct = default)
    {
        // Logic to get the status and result of the long-running execution...
    }
    
    public override Task<AgentRunResponse> UpdateAsyncRunAsync(string runId, AgentThread? thread = null, IList<ChatMessage> chatMessages, CancellationToken ct = default)
    {
        // Logic to update the long-running execution...
    }

    public override Task<AgentRunResponse> CancelAsyncRunAsync(string runId, AgentThread? thread = null, CancellationToken ct = default)
    {
        // Logic to cancel the long-running execution...
    }

    // Override other methods and properties as needed...
}
```

Example of handling both long-running executions and quick prompts:

```csharp
AIAgent agent = new CustomAgent(asynchronousRun: true);

AgentThread thread = agent.GetNewThread();

// Start a long-running execution for the prompt
AgentRunResponse response = await agent.RunAsync("<prompt>", thread);

// Check if the response contains an AsyncRunContent item indicating a long-running execution
if (GetAsyncRunContent(response) is AsyncRunContent asyncRunContent)
{
    AgentRunResponse? result = null;

    // Poll for the status of the long-running execution
    while (asyncRunContent.Status is AsyncRunStatus.InProgress or AsyncRunStatus.Queued)
    {
        result = await agent.GetAsyncRunResultAsync(asyncRunContent.RunId, thread);
    }
    
    Console.WriteLine(result);
}
else
{
    // The response is a quick prompt completion
    Console.WriteLine(response);
}
```

Example of cancelling a long-running execution:

```csharp
AIAgent agent = new CustomAgent(asynchronousRun: true);

AgentThread thread = agent.GetNewThread();

// Start a long-running execution for the prompt
AgentRunResponse response = await agent.RunAsync("<prompt>", thread);

if (GetAsyncRunContent(response) is AsyncRunContent asyncRunContent)
{
    int attempts = 0;

    // Poll for the status of the long-running execution
    while (asyncRunContent.Status is AsyncRunStatus.InProgress or AsyncRunStatus.Queued)
    {
        response = await agent.GetAsyncRunResultAsync(asyncRunContent.RunId, thread);

        if(attempts++ > 10)
        {
            // Cancel the long-running execution if it is still in progress after 10 attempts
            if (agent.CanCancelAsyncRun)
            {
                await agent.CancelAsyncRunAsync(asyncRunContent.RunId, thread);
            }
         
            return;
        }
    }
    
    Console.WriteLine(response);
}
```

Example of specifying long-running execution mode per invocation of the `RunAsync` method:

```csharp
// Run all prompts as long-running executions
AIAgent agent = new CustomAgent(asynchronousRun: true);

AgentThread thread = agent.GetNewThread();

// Start a long-running execution for the prompt
AgentRunResponse response = await agent.RunAsync("<prompt>", thread);

// Same as above, but explictly specify long-running execution mode
response = await agent.RunAsync("<prompt>", thread, new AgentRunOptions { AsynchronousRun = true });

// Run a quick prompt
response = await agent.RunAsync("<prompt>", thread, new AgentRunOptions { AsynchronousRun = false });
```

## Decision Outcome
TBD
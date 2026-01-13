---
status: accepted
contact: sergeymenshykh
date: 2025-10-15
deciders: markwallace, rbarreto, westey-m, stephentoub
informed: {}
---

## Long-Running Operations Design

## Context and Problem Statement

The Agent Framework currently supports synchronous request-response patterns for AI agent interactions, 
where agents process requests and return results immediately. Similarly, MEAI chat clients follow the same 
synchronous pattern for AI interactions. However, many real-world AI scenarios involve complex tasks that 
require significant processing time, such as:
- Code generation and analysis tasks
- Complex reasoning and research operations  
- Image and content generation
- Large document processing and summarization

The current Agent Framework architecture needs native support for long-running operations, as it is
essential for handling these scenarios effectively. Additionally, as MEAI chat clients need to start supporting 
long-running operations as well to be used together with AF agents, the design should consider integration 
patterns and consistency with the broader Microsoft.Extensions.AI ecosystem to provide a unified experience 
across both agent and chat client scenarios.

## Decision Drivers
- Chat clients and agents should support long-running execution as well as quick prompts.
- The design should be simple and intuitive for developers to use.
- The design should be extensible to allow new long-running execution features to be added in the future.
- The design should be additive rather than disruptive to allow existing chat clients to iteratively add 
support for long-running operations without breaking existing functionality.

## Comparison of Long-Running Operation Features
|        Feature              | OpenAI Responses          | Foundry Agents                      | A2A                  |
|-----------------------------|---------------------------|-------------------------------------|----------------------|
| Initiated by                | User (Background = true)  | Long-running execution is always on | Agent                |
| Modeled as 			      | Response                  | Run                                 | Task                 |
| Supported modes<sup>1</sup> | Sync, Async               | Async                               | Sync, Async          |
| Getting status support      | ✅                        | ✅                                 | ✅                   |
| Getting result support      | ✅                        | ✅                                 | ✅                   |
| Update support              | ❌                        | ❌                                 | ✅                   |
| Cancellation support        | ✅                        | ✅                                 | ✅                   |
| Delete support              | ✅                        | ❌                                 | ❌                   |
| Non-streaming support       | ✅                        | ✅                                 | ✅                   |
| Streaming support           | ✅                        | ✅                                 | ✅                   |
| Execution statuses          | InProgress, Completed, Queued <br/>Cancelled, Failed, Incomplete | InProgress, Completed, Queued<br/>Cancelled, Failed, Cancelling, <br/>RequiresAction, Expired |  Working, Completed, Canceled, <br/>Failed, Rejected, AuthRequired, <br/>InputRequired, Submitted, Unknown |

<sup>1</sup> Sync is a regular message-based request/response communication pattern; Async is a pattern for long-running operations/tasks where the agent returns an ID for a run/task and allows polling for status and final results by the ID.

**Note:** The names for new classes, interfaces, and their members used in the sections below are tentative and will be discussed in a dedicated section of this document.

## Long-Running Operations Support for Chat Clients

This section describes different options for various aspects required to add long-running operations support to chat clients.

### 1. Methods for Working with Long-Running Operations

Based on the analysis of existing APIs that support long-running operations (such as OpenAI Responses, Azure AI Foundry Agents, and A2A), 
the following operations are used for working with long-running operations:
- Common operations:
  - **Start Long-Running Execution**: Initiates a long-running operation and returns its Id.
  - **Get Status of Long-Running Execution**: This method retrieves the status of a long-running operation.
  - **Get Result of Long-Running Execution**: Retrieves the result of a long-running operation.
- Uncommon operations:
  - **Update Long-Running Execution**: This method updates a long-running operation, such as adding new messages or modifying existing ones.
  - **Cancel Long-Running Execution**: This method cancels a long-running operation.
  - **Delete Long-Running Execution**: This method deletes a long-running operation.

To support these operations by `IChatClient` implementations, the following options are available:
- **1.1 New IAsyncChatClient Interface for All Long-Running Execution Operations**
- **1.2 Get{Streaming}ResponseAsync for Common Operations & New IAsyncChatClient Interface for Uncommon Operations**
- **1.3 Get{Streaming}ResponseAsync for Common Operations & New IAsyncChatClient Interface for Uncommon Operations & Capability Check**
- **1.4 Get{Streaming}ResponseAsync for Common Operations & Individual Interface per Uncommon Operation**

#### 1.1 New IAsyncChatClient Interface for All Long-Running Execution Operations

This option suggests adding a new interface `IAsyncChatClient` that some implementations of `IChatClient` may implement to support long-running operations.
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
        Console.WriteLine("This chat client does not support long-running operations.");
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
    result = await asyncChatClient.GetAsyncRunStatusAsync(asyncRunContent.RunId);
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
- Callers can determine if a chat client supports long-running operations by calling its `GetService<IAsyncChatClient>()` method.

**Cons:**
- Not extensible: Adding new methods to the `IAsyncChatClient` interface after its release will break existing implementations of the interface.
- Missing capability check: Callers cannot determine if chat clients support specific uncommon operations before attempting to use them.
- Insufficient information: Callers may not have enough information to decide whether a prompt should run as a long-running operation.
- The new method calls bypass existing decorators such as logging, telemetry, etc.
- An alternative solution for decorating the new methods will have to be put in place because the new method calls bypass existing decorators 
such as logging, telemetry, etc.

#### 1.2 Get{Streaming}ResponseAsync for Common Operations & New IAsyncChatClient Interface for Uncommon Operations

This option suggests using the existing `GetResponseAsync` and `GetStreamingResponseAsync` methods of the `IChatClient` interface to support 
common long-running operations, such as starting long-running operations, getting their status, their results, and potentially 
updating them, in addition to their existing functionality of serving quick prompts. Methods for the uncommon operations, such as updating, 
cancelling, and deleting long-running operations, will be added to a new `IAsyncChatClient` interface that will be implemented by chat clients 
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
        if(enableLongRunningResponses)
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
        throw new NotSupportedException("This chat client does not support updating long-running operations.");
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
    response = await chatClient.GetResponseAsync([], new ChatOptions
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
            Console.WriteLine("This chat client does not support cancelling long-running operations.");
        }
        
        try
        {
            await asyncChatClient?.DeleteAsyncRunAsync(asyncRunContent.RunId);
        }
        catch (NotSupportedException)
        {
            Console.WriteLine("This chat client does not support deleting long-running operations.");
        }
    }
}
else
{
    // Handle the case when the response is a quick prompt completion
    Console.WriteLine(response);
}
```

This option addresses the issue that the option above has with callers needing to know whether the prompt should 
be run as a long-running operation or a quick prompt. It allows callers to simply call the existing `GetResponseAsync` method, 
and the chat client will decide whether to run the prompt as a long-running operation or a quick prompt. If control over 
the execution mode is still needed, and the underlying API supports it, it will be possible for callers to set the mode at 
the chat client invocation or configuration. More details about this are provided in one of the sections below about enabling long-running operation mode.
  
Additionally, it addresses another issue where the `GetResponseAsync` method may return a long-running
execution response and the `StartAsyncRunAsync` method may return a quick prompt response. Having one method that handles both cases
allows callers to not worry about this behavior and simply check the type of the response to determine if it is a long-running operation
or a quick prompt completion.

With the `GetResponseAsync` method becoming responsible for starting, getting status, getting results and updating long-running operations,
there are only a few operations left in the `IAsyncChatClient` interface - cancel and delete. As a result, the `IAsyncChatClient` interface
name may not be the best fit, as it suggests that it is responsible for all long-running operations while it is not. Should 
the interface be renamed to reflect the operations it supports? What should the new name be? Option 1.4 considers an alternative
that might solve the naming issue. 

**Pros:**
- Delegation and control: Callers delegate the decision of whether to run a prompt as a long-running operation or quick prompt to chat clients,
while still having the option to control the execution mode to determine how to handle prompts if needed.
- Not a breaking change: Existing chat clients are not affected. 
  
**Cons:**  
- Not extensible: Adding new methods to the `IAsyncChatClient` interface after its release will break existing implementations of the interface. 
- Missing capability check: Callers cannot determine if chat clients support specific uncommon operations before attempting to use them.
- An alternative solution for decorating the new methods will have to be put in place because the new method calls bypass existing decorators 
such as logging, telemetry, etc.

#### 1.3 Get{Streaming}ResponseAsync for Common Operations & New IAsyncChatClient Interface for Uncommon Operations & Capability Check

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

    public bool CanUpdateAsyncRun => false; // This chat client does not support updating long-running operations.
    public bool CanCancelAsyncRun => true;  // This chat client supports cancelling long-running operations.
    public bool CanDeleteAsyncRun => true;  // This chat client supports deleting long-running operations.

    public Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken ct = default)
    {
        throw new NotSupportedException("This chat client does not support updating long-running operations.");
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
    response = await chatClient.GetResponseAsync([], new ChatOptions
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
- Delegation and control: Callers delegate the decision of whether to run a prompt as a long-running execution or quick prompt to chat clients,
while still having the option to control the execution mode to determine how to handle prompts if needed.
- Not a breaking change: Existing chat clients are not affected. 
- Capability check: Callers can determine if the chat client supports an uncommon operation before attempting to use it.
  
**Cons:**  
- Not extensible: Adding new members to the `IAsyncChatClient` interface after its release will break existing implementations of the interface.  
- An alternative solution for decorating the new methods will have to be put in place because the new method calls bypass existing decorators 
such as logging, telemetry, etc.

#### 1.4 Get{Streaming}ResponseAsync for Common Operations & Individual Interface per Uncommon Operation

This option suggests using the existing `Get{Streaming}ResponseAsync` methods of the `IChatClient` interface to support 
common long-running operations, such as starting long-running operations, getting their status, and their results, and potentially 
updating them, in addition to their existing functionality of serving quick prompts.

The uncommon operations that are not supported by all analyzed APIs, such as updating (which can be handled by `Get{Streaming}ResponseAsync`), cancelling, 
and deleting long-running operations, as well as future ones, will be added to their own interfaces that will be implemented by chat clients 
that support them.

This option presumes that Option 3.2 (Have one method for getting long-running execution status and result) is selected.

The interfaces can inherit from `IChatClient` to allow callers to use an instance of `ICancelableChatClient`, `IUpdatableChatClient`, or `IDeletableChatClient` 
for calling the `Get{Streaming}ResponseAsync` methods as well. However, those methods belong to a leaf chat client that, if obtained via the `GetService<T>()` 
method, won't be decorated by existing decorators such as function invocation, logging, etc. As a result, an alternative solution (wrap the instance of the leaf 
chat client in a decorator at the `GetService` method call) will need to be applied not only to the new methods of one of the interfaces but also to the existing
`Get{Streaming}ResponseAsync` ones.

```csharp
public interface ICancelableChatClient
{  
    Task<AsyncRunResult> CancelAsyncRunAsync(string runId, CancellationToken cancellationToken = default);
}

public interface IUpdatableChatClient
{  
    Task<AsyncRunResult> UpdateAsyncRunAsync(string runId, IList<ChatMessage> chatMessages, CancellationToken cancellationToken = default);
}

public interface IDeletableChatClient
{  
    Task<AsyncRunResult> DeleteAsyncRunAsync(string runId, CancellationToken cancellationToken = default);
}

// Responses chat client that supports standard long-running operations + cancellation and deletion
public class ResponsesChatClient : IChatClient, ICancelableChatClient, IDeletableChatClient
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

Example that starts a long-running operation, gets its status, and cancels and deletes it if it's not completed after some time:
```csharp
IChatClient chatClient = new ResponsesChatClient();

ChatResponse response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AllowLongRunningResponses = true });

if (GetAsyncRunContent(response) is AsyncRunContent asyncRunContent)
{
    // Get result
    response = await chatClient.GetResponseAsync([], new ChatOptions
    { 
        RunId = asyncRunContent.RunId 
    });

    // After some time

    // If it's still running, cancel and delete the run
    if (GetAsyncRunContent(response).Status is AsyncRunStatus.InProgress or AsyncRunStatus.Queued)
    {
        if(chatClient.GetService<ICancelableChatClient>() is {} cancelableChatClient)
        {
            await cancelableChatClient.CancelAsyncRunAsync(asyncRunContent.RunId);
        }

        if(chatClient.GetService<IDeletableChatClient>() is {} deletableChatClient)
        {
            await deletableChatClient.DeleteAsyncRunAsync(asyncRunContent.RunId);
        }
    }
}
```

**Pros:**
- Extensible: New interfaces can be added and implemented to support new long-running operations without breaking 
existing chat client implementations.
- Not a breaking change: Existing chat clients that implement the `IChatClient` interface are not affected.
- Delegation and control: Callers delegate the decision of whether to run a prompt as a long-running operation or quick prompt
to chat clients, while still having the option to control the execution mode to determine how to handle prompts if needed.
  
**Cons:**  
- Breaking changes: Changing the signatures of the methods of the operation-specific interfaces or adding new members to them will 
break existing implementations of those interfaces. However, the blast radius of this change is much smaller and limited to a subset
of chat clients that implement the operation-specific interfaces. However, this is still a breaking change.

### 2. Enabling Long-Running Operations

Based on the API analysis, some APIs must be explicitly configured to run in long-running operation mode, 
while others don't need additional configuration because they either decide themselves whether a request
should run as a long-running operation, or they always operate in long-running operation mode or quick prompt mode:
|        Feature              | OpenAI Responses          | Foundry Agents                      | A2A                  |
|-----------------------------|---------------------------|-------------------------------------|----------------------|
| Long-running execution      | User (Background = true)  | Long-running execution is always on | Agent                |

The options below consider how to enable long-running operation mode for chat clients that support both quick prompts and long-running operations.

#### 2.1 Execution Mode per `Get{Streaming}ResponseAsync` Invocation

This option proposes adding a new nullable `AllowLongRunningResponses` property to the `ChatOptions` class.
The property value will be `true` if the caller requests a long-running operation, `false`, `null` or omitted otherwise.
  
Chat clients that work with APIs requiring explicit configuration per operation will use this property to determine whether to run the prompt as a long-running 
operation or quick prompt. Chat clients that work with APIs that don't require explicit configuration will ignore this property and operate according 
to their own logic/configuration.

```csharp
public class ChatOptions
{
    // Existing properties...
    public bool? AllowLongRunningResponses { get; set; }
}

// Consumer code example
IChatClient chatClient = ...; // Get an instance of IChatClient

// Start a long-running execution for the prompt if supported by the underlying API
ChatResponse response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AllowLongRunningResponses = true });

// Start a quick prompt
ChatResponse quickResponse = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AllowLongRunningResponses = false });
```

**Pros:** 
- Callers can switch between quick prompts and long-running operation per invocation of the `Get{Streaming}ResponseAsync` methods without 
changing the client configuration.
- Enables explicit control over the execution mode by callers per invocation, meaning that no caller site is broken if the agent is injected via DI, 
and the caller can turn on the long-running operation mode when it can handle it.

**Con:** This may not be valuable for all callers, as they may not have enough information to decide whether the prompt should run as a long-running operation or quick prompt.

#### 2.2 Execution Mode per `Get{Streaming}ResponseAsync` Invocation + Model Class

This option is similar to the previous one, but suggest using a model class `LongRunningResponsesOptions` for properties related to long-running operations.

```csharp
public class LongRunningResponsesOptions
{
    public bool? Allow { get; set; }
    //public PollingSettings? PollingSettings { get; set; } // Can be added leter if necessary
}

public class ChatOptions
{
    public LongRunningResponsesOptions? LongRunningResponsesOptions { get; set; }
}

// Consumer code example
IChatClient chatClient = ...; // Get an instance of IChatClient

// Start a long-running execution for the prompt if supported by the underlying API
ChatResponse response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { LongRunningResponsesOptions = new() { Allow = true } });
```

**Pros:** 
- Enables explicit control over the execution mode by callers per invocation, meaning that no caller site is broken if the agent is injected via DI, 
and the caller can turn on the long-running operation mode when it can handle it.
- No proliferation of long-running operation-related properties in the `ChatOptions` class.

**Con:** Slightly more complex initialization.

#### 2.3 Execution Mode per Chat Client Instance

This option proposes adding a new `enableLongRunningResponses` parameter to constructors of chat clients that support both quick prompts and long-running operations.
The parameter value will be `true` if the chat client should operate in long-running operation mode, `false` if it should operate in quick prompt mode.

Chat clients that work with APIs requiring explicit configuration will use this parameter to determine whether to run prompts as long-running operations or quick prompts.
Chat clients that work with APIs that don't require explicit configuration won't have this parameter in their constructors and will operate according to their own 
logic/configuration.

```csharp
public class CustomChatClient : IChatClient
{
    private readonly bool _enableLongRunningResponses;

    public CustomChatClient(bool enableLongRunningResponses)
    {
        this._enableLongRunningResponses = enableLongRunningResponses;
    }

    // Existing methods...
}

// Consumer code example
IChatClient chatClient = new CustomChatClient(enableLongRunningResponses: true);

// Start a long-running execution for the prompt
ChatResponse response = await chatClient.GetResponseAsync("<prompt>");
```

Chat clients can be configured to always operate in long-running operation mode or quick prompt mode based on their role in a specific scenario.
For example, a chat client responsible for generating ideas for images can be configured for quick prompt mode, while a chat client responsible for image 
generation can be configured to always use long-running operation mode.

**Pro:** Can be beneficial for scenarios where chat clients need to be configured upfront in accordance with their role in a scenario.

**Con:** Less flexible than the previous option, as it requires configuring the chat client upfront at instantiation time. However, this flexibility might not be needed.

#### 2.4 Combined Approach

This option proposes a combined approach that allows configuration per chat client instance and per `Get{Streaming}ResponseAsync` method invocation.

The chat client will use whichever configuration is provided, whether set in the chat client constructor or in the options for the `Get{Streaming}ResponseAsync` 
method invocation. If both are set, the one provided in the `Get{Streaming}ResponseAsync` method invocation takes precedence.

```csharp
public class CustomChatClient : IChatClient
{
    private readonly bool _enableLongRunningResponses;

    public CustomChatClient(bool enableLongRunningResponses)
    {
        this._enableLongRunningResponses = enableLongRunningResponses;
    }
    
    public async Task<ChatResponse> GetResponseAsync(string prompt, ChatOptions? options = null, CancellationToken ct = default)
    {
        bool enableLongRunningResponses = options?.AllowLongRunningResponses ?? this._enableLongRunningResponses;
        // Logic to handle the prompt based on enableLongRunningResponses...
    }
}

// Consumer code example
IChatClient chatClient = new CustomChatClient(enableLongRunningResponses: true);

// Start a long-running execution for the prompt
ChatResponse response = await chatClient.GetResponseAsync("<prompt>");

// Start a quick prompt
ChatResponse quickResponse = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AllowLongRunningResponses = false });
```

**Pros:** Flexible approach that combines the benefits of both previous options.

### 3. Getting Status and Result of Long-Running Execution

The explored APIs use different approaches for retrieving the status and results of long-running operations. Some are using
one method to retrieve both status and result, while others use two separate methods for each operation:
|        Feature              | OpenAI Responses              | Foundry Agents                                     | A2A                   |
|-------------------|-------------------------------|----------------------------------------------------|-----------------------|
| API to Get Status | GetResponseAsync(responseId)  | Runs.GetRunAsync(thread.Id, threadRun.Id)          | GetTaskAsync(task.Id) |
| API to Get Result | GetResponseAsync(responseId)  | Messages.GetMessagesAsync(thread.Id, threadRun.Id) | GetTaskAsync(task.Id) |

Taking into account the differences, the following options propose a few ways to model the API for getting the status and result of 
long-running operations for the `AIAgent` interface implementations.

#### 3.1 Two Separate Methods for Status and Result

This option suggests having two separate methods for getting the status and result of long-running operations:
```csharp
public interface IAsyncChatClient
{
    Task<AsyncRunResult> GetAsyncRunStatusAsync(string runId, CancellationToken ct = default);
    Task<AsyncRunResult> GetAsyncRunResultAsync(string runId, CancellationToken ct = default);
}
```

**Pros:** Could be more intuitive for developers, as it clearly separates the concerns of checking the status and retrieving the result of a long-running operation.

**Cons:** Creates inefficiency for chat clients that use APIs that return both status and result in a single call, 
as callers might make redundant calls to get the result after checking the status that already contains the result.

#### 3.2 One Method to Get Status and Result

This option suggests having a single method for getting both the status and result of long-running operations:
```csharp
public interface IAsyncChatClient
{
    Task<AsyncRunResult> GetAsyncRunResultAsync(string runId, AgentThread? thread = null, CancellationToken ct = default);
}
```

This option will redirect the call to the appropriate method of the underlying API that uses one method to retrieve both.
For APIs that use two separate methods, the method will first get the status and if the status indicates that the 
operation is still running, it will return the status to the caller. If the status indicates that the operation is completed,
it will then call the method to get the result of the long-running operation and return it together with the status.

**Pros:**
- Simplifies the API by providing a single, intuitive method for retrieving long-running operation information.
- More optimal for chat clients that use APIs that return both status and result in a single call, as it avoids unnecessary API calls.

### 4. Place For RunId, Status, and UpdateId of Long-Running Operations

This section considers different options for exposing the `RunId`, `Status`, and `UpdateId` properties of long-running operations.

#### 4.1. As AIContent

The `AsyncRunContent` class will represent a long-running operation initiated and managed by an agent/LLM.
Items of this content type will be returned in a chat message as part of the `AgentRunResponse` or `ChatResponse`
response to represent the long-running operation.

The `AsyncRunContent` class has two properties: `RunId` and `Status`. The `RunId` identifies the 
long-running operation, and the `Status` represents the current status of the operation. The class  
inherits from `AIContent`, which is a base class for all AI-related content in MEAI and AF.

The `AsyncRunStatus` class represents the status of a long-running operation. Initially, it will have 
a set of predefined statuses that represent the possible statuses used by existing Agent/LLM APIs that support
long-running operations. It will be extended to support additional statuses as needed while also
allowing custom, not-yet-defined statuses to propagate as strings from the underlying API to the callers.

The content class type can be used by both agents and chat clients to represent long-running operations.
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
This UpdateId should be available together with RunId to callers, allowing them to resume a long-running operation identified 
by the RunId from the last received update, identified by the UpdateId.

#### 4.2. As Properties Of ChatResponse{Update}

This option suggests adding properties related to long-running operations directly to the `ChatResponse` and `ChatResponseUpdate` classes rather 
than using a separate content class for that. See section "6. Model To Support Long-Running Operations" for more details.

### 5. Streaming Support

All analyzed APIs that support long-running operations also support streaming. 

Some of them natively support resuming streaming from a specific point in the stream, while for others, this is either implementation-dependent or needs to be emulated:

| API                     | Can Resume Streaming                 | Model                                                                                                      |
|-------------------------|--------------------------------------|------------------------------------------------------------------------------------------------------------|
| OpenAI Responses        | Yes                                  | StreamingResponseUpdate.**SequenceNumber** + GetResponseStreamingAsync(responseId, **startingAfter**, ct)  |
| Azure AI Foundry Agents | Emulated<sup>2</sup>                 | RunStep.**Id** + custom pseudo code: client.Runs.GetRunStepsAsync(...).AllStepsAfter(**stepId**)           |
| A2A                     | Implementation dependent<sup>1</sup> |          																				                  |

<sup>1</sup> The [A2A specification](https://github.com/a2aproject/A2A/blob/main/docs/topics/streaming-and-async.md#1-streaming-with-server-sent-events-sse)
allows an A2A agent implementation to decide how to handle streaming resumption: _If a client's SSE connection breaks prematurely while 
a task is still active (and the server hasn't sent a final: true event for that phase), the client can attempt to reconnect to the stream using the tasks/resubscribe RPC method. 
The server's behavior regarding missed events during the disconnection period (e.g., whether it backfills or only sends new updates) is implementation-dependent._

<sup>2</sup> The Azure AI Foundry Agents API has an API to start a streaming run but does not have an API to resume streaming from a specific point in the stream.
However, it has non-streaming APIs to access already started runs, which can be used to emulate streaming resumption by accessing a run and its steps and streaming all the steps after a specific step.

#### Required Changes

To support streaming resumption, the following model changes are required:

- The `ChatOptions` class needs to be extended with a new `StartAfter` property that will identify an update to resume streaming from and to start generating responses after.
- The `ChatResponseUpdate` class needs to be extended with a new `SequenceNumber` property that will identify the update number within the stream.

All the chat clients supporting the streaming resumption will need to return the `SequenceNumber` property as part of the `ChatResponseUpdate` class and 
honor the `StartAfter` property of the `ChatOptions` class.

#### Function Calling

Function calls over streaming are communicated to chat clients through a series of updates. Chat clients accumulate these updates in their internal state to build
the function call content once the last update has been received. The completed function call content is then returned to the function-calling chat client, 
which eventually invokes it.

Since chat clients keep function call updates in their internal state, resuming streaming from a specific update can be impossible if the resumption request 
is made using a chat client that does not have the previous updates stored. This situation can occur if a host suspends execution during an ongoing function call 
stream and later resumes from that particular update. Because chat clients' internal state is not persisted, they will lack the prior updates needed to continue 
the function call, leading to a failure in resumption.

To address this issue, chat clients can only return sequence numbers for updates that are resumable. For updates that cannot be resumed from, chat clients can 
return the sequence number of the most recent update received before the non-resumable one. This allows callers to resume from that earlier update,
even if it means re-processing some updates that have already been handled.

Chat clients will continue returning the sequence number of the last resumable update until a new resumable update becomes available. For example, a chat client might 
keep returning sequence number 2, corresponding to the last resumable update received before an update for the first function call. Once **all** function call updates 
are received and processed, and the model returns a non-function call response, the chat client will then return a sequence number, say 10, which corresponds to the 
first non-function call update. 

##### Status of Streaming Updates

Different APIs provide different statuses for streamed function call updates

Sequence of updates from OpenAI Responses API to answer the question "What time is it?" using a function call:
| Id     | SN | Update.Kind              | Response.Status | ChatResponseUpdate.Status | Description                                       |
|--------|----|--------------------------|-----------------|---------------------------|---------------------------------------------------|
| resp_1 | 0  | resp.created             | Queued          | Queued                    |                                                   |
| resp_1 | 1  | resp.queued              | Queued          | Queued                    |                                                   |
| resp_1 | 2  | resp.in_progress         | InProgress      | InProgress                |                                                   |
| resp_1 | 3  | resp.output_item.added   | -               | InProgress                |                                                   |
| resp_1 | 4  | resp.func_call.args.delta| -               | InProgress                |                                                   |
| resp_1 | 5  | resp.func_call.args.done | -               | InProgress                |                                                   |
| resp_1 | 6  | resp.output_item.done    | -               | InProgress                |                                                   |
| resp_1 | 7  | resp.completed           | Completed       | Complete                  |                                                   |
| resp_1 | -  | -                        | -               | null                      | FunctionInvokingChatClient yields function result  |
|        |    |                          | OpenAI Responses created a new response to handle function call result                          |
| resp_2 | 0  | resp.created             | Queued          | Queued                    |                                                   |
| resp_2 | 1  | resp.queued              | Queued          | Queued                    |                                                   |
| resp_2 | 2  | resp.in_progress         | InProgress      | InProgress                |                                                   |
| resp_2 | 3  | resp.output_item.added   | -               | InProgress                |                                                   |
| resp_2 | 4  | resp.cnt_part.added      | -               | InProgress                |                                                   |
| resp_2 | 5  | resp.output_text.delta   | -               | InProgress                |                                                   |
| resp_2 | 6  | resp.output_text.delta   | -               | InProgress                |                                                   |
| resp_2 | 7  | resp.output_text.delta   | -               | InProgress                |                                                   |
| resp_2 | 8  | resp.output_text.done    | -               | InProgress                |                                                   |
| resp_2 | 9  | resp.cnt_part.done       | -               | InProgress                |                                                   |
| resp_2 | 10 | resp.output_item.done    | -               | InProgress                |                                                   |
| resp_2 | 11 | resp.completed           | Completed       | Completed                 |                                                   |

Sequence of updates from Azure AI Foundry Agents API to answer the question "What time is it?" using a function call:
| Id     | SN      | UpdateKind        | Run.Status     | Step.Status | Message.Status  | ChatResponseUpdate.Status | Description                                       |
|--------|---------|-------------------|----------------|-------------|-----------------|---------------------------|---------------------------------------------------|
| run_1  | -       | RunCreated        | Queued         | -           | -               | Queued                    |                                                   |
| run_1  | step_1  | -                 | RequiredAction | InProgress  | -               | RequiredAction            |                                                   |
| TBD	 | -	   | -				   | -              | -           | -               | -                         | FunctionInvokingChatClient yields function result  |
| run_1  | -       | RunStepCompleted  | Completed      | -           | -               | InProgress                |                                                   |
| run_1  | -	   | RunQueued         | Queued		    | -           | -               | Queued                    |                                                   |
| run_1  | -	   | RunInProgress     | InProgress	    | -           | -               | InProgress                |                                                   |
| run_1  | step_2  | RunStepCreated    | -              | InProgress  | -               | InProgress                |                                                   |
| run_1  | step_2  | RunStepInProgress | -              | InProgress  | -               | InProgress                |                                                   |
| run_1  | -       | MessageCreated    | -              | -           | InProgress      | InProgress                |                                                   |
| run_1  | -       | MessageInProgress | -              | -           | InProgress      | InProgress                |                                                   |
| run_1  | -       | MessageUpdated    | -              | -           | -               | InProgress                |                                                   |
| run_1  | -       | MessageUpdated    | -              | -           | -               | InProgress                |                                                   |
| run_1  | -       | MessageUpdated    | -              | -           | -               | InProgress                |                                                   |
| run_1  | -       | MessageCompleted  | -              | -           | Completed       | InProgress                |                                                   |
| run_1  | step_2  | RunStepCompleted  | Completed      | -           | -               | InProgress                |                                                   |
| run_1  | -       | RunCompleted      | Completed      | -           | -               | Completed                 |                                                   |

### 6. Model To Support Long-Running Operations

To support long-running operations, the following values need to be returned by the GetResponseAsync and GetStreamingResponseAsync methods:
- `ResponseId` - identifier of the long-running operation or an entity representing it, such as a task.
- `ConversationId` - identifier of the conversation or thread the long-running operation is part of. Some APIs, like Azure AI Foundry Agents, use 
  this identifier together with the ResponseId to identify a run.
- `SequenceNumber` - identifier of an update within a stream of updates. This is required to support streaming resumption by the GetStreamingResponseAsync method only.
- `Status` - status of the long-running operation: whether it is queued, running, failed, cancelled, completed, etc.

These values need to be supplied to subsequent calls of the GetResponseAsync and GetStreamingResponseAsync methods to get the status and result of long-running operations.

#### 6.1 ChatOptions

The following options consider different ways of extending the `ChatOptions` class to include the following properties to support long-running operations:
- `AllowLongRunningResponses` - a boolean property that indicates whether the caller allows the chat client to run in long-running operation mode if it's supported by the chat client.
- `ResponseId` - a string property that represents the identifier of the long-running operation or an entity representing it. A non-null value of this property would indicate to chat clients
that callers want to get the status and result of an existing long-running operation, identified by the property value, rather than starting a new one.
- `StartAfter` - a string property that represents the sequence number of an update within a stream of updates so that the chat client can resume streaming after the last received update.

##### 6.1.1 Direct Properties in ChatOptions

```csharp
public class ChatOptions
{
    // Existing properties...
    /// <summary>Gets or sets an optional identifier used to associate a request with an existing conversation.</summary>
    public string? ConversationId { get; set; }
    ...

    // New properties...
    public bool? AllowLongRunningResponses { get; set; }
    public string? ResponseId { get; set; }
    public string? StartAfter { get; set; }
}

// Usage example
var response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AllowLongRunningResponses = true });

// If the response indicates a long-running operation, get its status and result
if(response.Status is {} status)
{
    response = await chatClient.GetResponseAsync([], new ChatOptions 
    { 
        AllowLongRunningResponses = true,
        ResponseId = response.ResponseId,
        ConversationId = response.ConversationId,
        //StartAfter = response.SequenceNumber // for GetStreamingResponseAsync only
    });
}

```

**Con:** Proliferation of long-running operation properties in the `ChatOptions` class.

##### 6.1.2 LongRunOptions Model Class

```csharp
public class ChatOptions
{
    // Existing properties...
    public string? ConversationId { get; set; } 
    ...
    
    // New properties...
    public bool? AllowLongRunningResponses { get; set; }

    public LongRunOptions? LongRunOptions { get; set; }
}

public class LongRunOptions
{
    public string? ResponseId { get; set; }
    public string? ConversationId { get; set; } 
    public string? StartAfter { get; set; }

    // Alternatively, ChatResponse can have an extension method ToLongRunOptions.
    public LongRunOptions FromChatResponse(ChatResponse response)
    {
        return new LongRunOptions
        {
            ResponseId = response.ResponseId,
            ConversationId = response.ConversationId,
        };
    }

    // Alternatively, ChatResponseUpdate can have an extension method ToLongRunOptions.
    public LongRunOptions FromChatResponseUpdate(ChatResponseUpdate update)
    {
        return new LongRunOptions
        {
            ResponseId = update.ResponseId,
            ConversationId = update.ConversationId,
            StartAfter = update.SequenceNumber,
        };
    }
}

// Usage example
var response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AllowLongRunningResponses = true });

// If the response indicates a long-running operation, get its status and result
if(response.Status is {} status)
{
    while(status != ResponseStatus.Completed)
    {
        response = await chatClient.GetResponseAsync([], new ChatOptions 
        { 
            AllowLongRunningResponses = true,
            LongRunOptions = LongRunOptions.FromChatResponse(response)
            // or extension method
            LongRunOptions = response.ToLongRunOptions()
            // or implicit conversion
            LongRunOptions = response
        });
    }
}
```

**Pro:** No proliferation of long-running operation properties in the `ChatOptions` class.

**Con:** Duplicated property `ConversationId`.

##### 6.1.3 Continuation Token of System.ClientModel.ContinuationToken Type

This option suggests using `System.ClientModel.ContinuationToken` to encapsulate all properties required for long-running operations.
The continuation token will be returned by chat clients as part of the `ChatResponse` and `ChatResponseUpdate` responses to indicate that
the response is part of a long-running execution. A null value of the property will indicate that the response is not part of a long-running execution.
Chat clients will accept a non-null value of the property to indicate that callers want to get the status and result of an existing long-running operation.

Each chat client will implement its own continuation token class that inherits from `ContinuationToken` to encapsulate properties required for long-running operations
that are specific to the underlying API the chat client works with. For example, for the OpenAI Responses API, the continuation token class will encapsulate
the `ResponseId` and `SequenceNumber` properties.

```csharp
public class ChatOptions
{
    // Existing properties...
    public string? ConversationId { get; set; } 
    ...
    
    // New properties...
    public bool? AllowLongRunningResponses { get; set; }

    public ContinuationToken? ContinuationToken { get; set; }
}

internal sealed class LongRunContinuationToken : ContinuationToken
{
    public LongRunContinuationToken(string responseId)
    {
        this.ResponseId = responseId;
    }

    public string ResponseId { get; set; }

    public int? SequenceNumber { get; set; }

    public static LongRunContinuationToken FromToken(ContinuationToken token)
    {
        if (token is LongRunContinuationToken longRunContinuationToken)
        {
            return longRunContinuationToken;
        }

        BinaryData data = token.ToBytes();

        Utf8JsonReader reader = new(data);

        string responseId = null!;
        int? startAfter = null;

        reader.Read();

        // Reading functionality

        return new(responseId)
        {
            SequenceNumber = startAfter
        };
    }
}

// Usage example
ChatOptions options = new() { AllowLongRunningResponses = true };

var response = await chatClient.GetResponseAsync("<prompt>", options);

while (response.ContinuationToken is { } token)
{
    options.ContinuationToken = token;

    response = await chatClient.GetResponseAsync([], options);
}

Console.WriteLine(response.Text);
```

**Pro:** No proliferation of long-running operation properties in the `ChatOptions` class, including the `Status` property.

##### 6.1.4 Continuation Token of String Type

This options is similar to the previous one but suggests using a string type for the continuation token instead of the `System.ClientModel.ContinuationToken` type.

```csharp
internal sealed class LongRunContinuationToken
{
    public LongRunContinuationToken(string responseId)
    {
        this.ResponseId = responseId;
    }

    public string ResponseId { get; set; }

    public int? SequenceNumber { get; set; }

    public static LongRunContinuationToken Deserialize(string json)
    {
        Throw.IfNullOrEmpty(json);

        var token = JsonSerializer.Deserialize<LongRunContinuationToken>(json, OpenAIJsonContext2.Default.LongRunContinuationToken)
            ?? throw new InvalidOperationException("Failed to deserialize LongRunContinuationToken.");

        return token;
    }

    public string Serialize()
    {
        return JsonSerializer.Serialize(this, OpenAIJsonContext2.Default.LongRunContinuationToken);
    }
}

public class ChatOptions
{
    public string? ContinuationToken { get; set; }
}
```

**Pro:** No dependency on the `System.ClientModel` package.

##### 6.1.5 Continuation Token of a Custom Type

The option is similar the the "6.1.3 Continuation Token of System.ClientModel.ContinuationToken Type" option but suggests using a 
custom type for the continuation token instead of the `System.ClientModel.ContinuationToken` type.

**Pros**
- There is no dependency on the `System.ClientModel` package.   
- There is no ambiguity between extension methods for `IChatClient` that would occur if a new extension method, which accepts a continuation token of string type as the first parameter, is added.

#### 6.2 Overloads of GetResponseAsync and GetStreamingResponseAsync

This option proposes introducing overloads of the `GetResponseAsync` and `GetStreamingResponseAsync` methods that will accept long-running operation parameters directly:

```csharp
public interface ILongRunningChatClient
{
    Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        string responseId,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default);

    IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        string responseId,
        string? startAfter = null,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default);
}

public class CustomChatClient : IChatClient, ILongRunningChatClient
{
    ...
}

// Usage example
IChatClient chatClient = ...; // Get an instance of IChatClient

ChatResponse response = await chatClient.GetResponseAsync("<prompt>", new ChatOptions { AllowLongRunningResponses = true });

if(response.Status is {} status && chatClient.GetService<ILongRunningChatClient>() is {} longRunningChatClient)
{
    while(status != AsyncRunStatus.Completed)
    {
        response = await longRunningChatClient.GetResponseAsync([], response.ResponseId, new ChatOptions { ConversationId = response.ConversationId });
    }
    ...
}

```

**Pros:**
- No proliferation of long-running operation properties in the ChatOptions class, except for the new AllowLongRunningResponses property discussed in section 2.

**Cons:**
- Interface switching: Callers need to switch to the `ILongRunningChatClient` interface to get the status and result of long-running operations.
- An alternative solution for decorating the new methods will have to be put in place.

## Long-Running Operations Support for AF Agents

### 1. Methods for Working with Long-Running Operations

The design for supporting long-running operations by agents is very similar to that for chat clients because it is based on 
the same analysis of existing APIs and anticipated consumption patterns.

#### 1.1 Run{Streaming}Async Methods for Common Operations and the Update Operation + New Method Per Uncommon Operation

This option suggests using the existing `Run{Streaming}Async` methods of the `AIAgent` interface implementations to start, get results, and update long-running operations.

For cancellation and deletion of long-running operations, new methods will be added to the `AIAgent` interface implementations.

```csharp
public abstract class AIAgent
{
    // Existing methods...
    public Task<AgentRunResponse> RunAsync(string message, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) { ... }
    public IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(string message, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) { ... }

    // New methods for uncommon operations
    public virtual Task<AgentRunResponse?> CancelRunAsync(string id, AgentCancelRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return Task.FromResult<AgentRunResponse?>(null);
    }

    public virtual Task<AgentRunResponse?> DeleteRunAsync(string id, AgentDeleteRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        return Task.FromResult<AgentRunResponse?>(null);
    }
}

// Agent that supports update and cancellation
public class CustomAgent : AIAgent
{
    public override async Task<AgentRunResponse?> CancelRunAsync(string id, AgentCancelRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var response = await this._client.CancelRunAsync(id, options?.Thread?.ConversationId);

        return ConvertToAgentRunResponse(response); 
    }

    // No overload for DeleteRunAsync as it's not supported by the underlying API
}

// Usage
AIAgent agent = new CustomAgent();

AgentThread thread = agent.GetNewThread();

AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

response = await agent.CancelRunAsync(response.ResponseId, new AgentCancelRunOptions { Thread = thread });
```

In case an agent supports either or both cancellation and deletion of long-running operations, it will override the corresponding methods.
Otherwise, it won't override them, and the base implementations will return null by default.

Some agents, for example Azure AI Foundry Agents, require the thread identifier to cancel a run. To accommodate this requirement, the `CancelRunAsync` method
accepts an optional `AgentCancelRunOptions` parameter that allows callers to specify the thread associated with the run they want to cancel.

```csharp
public class AgentCancelRunOptions
{
    public AgentThread? Thread { get; set; }
}
```

Similar design considerations can be applied to the `DeleteRunAsync` method and the `AgentDeleteRunOptions` class.

Having options in the method signatures allows for future extensibility; however, they can be added later if needed to the method overloads.

**Pros:**
- Existing `Run{Streaming}Async` methods are reused for common operations.
- New methods for uncommon operations can be added in a non-breaking way.

### 2. Enabling Long-Running Operations

The options for enabling long-running operations are exactly the same as those discussed in section "2. Enabling Long-Running Operations" for chat clients:
- Execution Mode per `Run{Streaming}Async` Invocation
- Execution Mode per `Run{Streaming}Async` Invocation + Model Class
- Execution Mode per agent instance
- Combined Approach

Below are the details of the option selected for chat clients that is also selected for agents.

#### 2.1 Execution Mode per `Run{Streaming}Async` Invocation

This option proposes adding a new nullable `AllowLongRunningResponses` property of bool type to the `AgentRunOptions` class.
The property value will be `true` if the caller requests a long-running operation, `false`, `null` or omitted otherwise.
  
AI agents that work with APIs requiring explicit configuration per operation will use this property to determine whether to run the prompt as a long-running 
operation or quick prompt. Agents that work with APIs that don't require explicit configuration will ignore this property and operate according 
to their own logic/configuration.

```csharp
public class AgentRunOptions
{
    // Existing properties...
    public bool? AllowLongRunningResponses { get; set; }
}

// Consumer code example
AIAgent agent = ...; // Get an instance of an AIAgent

// Start a long-running execution for the prompt if supported by the underlying API
AgentRunResponse response = await agent.RunAsync("<prompt>", new AgentRunOptions { AllowLongRunningResponses = true });

// Start a quick prompt
AgentRunResponse response = await agent.RunAsync("<prompt>");
```

**Pros:** 
- Callers can switch between quick prompts and long-running operations per invocation of the `Run{Streaming}Async` methods without 
changing agent configuration.
- Enables explicit control over the execution mode by callers per invocation, meaning that no caller site is broken if the agent is injected via DI, 
and the caller can turn on the long-running operation mode when it can handle it.

**Con:** This may not be valuable for all callers, as they may not have enough information to decide whether the prompt should run as a long-running operation or quick prompt.

### 3. Model To Support Long-Running Operations

The options for modeling long-running operations are exactly the same as those for chat clients discussed in section "6. Model To Support Long-Running Operations" above:
- Direct Properties in ChatOptions
- LongRunOptions Model Class
- Continuation Token of System.ClientModel.ContinuationToken Type
- Continuation Token of String Type
- Continuation Token of a Custom Type

Below are the details of the option selected for chat clients that is also selected for agents.
  
#### 3.1 Continuation Token of a Custom Type

This option suggests using `ContinuationToken` to encapsulate all properties representing a long-running operation. The continuation token will be returned by agents in the 
`ContinuationToken` property of the `AgentRunResponse` and `AgentRunResponseUpdate` responses to indicate that the response is part of a long-running operation. A null value 
of the property will indicate that the response is not part of a long-running operation or the long-running operation has been completed. Callers will set the token in the
`ContinuationToken` property of the `AgentRunOptions` class in follow-up calls to the `Run{Streaming}Async` methods to indicate that they want to "continue" the long-running
operation identified by the token.

Each agent will implement its own continuation token class that inherits from `ContinuationToken` to encapsulate properties required for long-running operations that are
specific to the underlying API the agent works with. For example, for the A2A agent, the continuation token class will encapsulate the `TaskId` property.

```csharp
internal sealed class A2AAgentContinuationToken : ResponseContinuationToken
{
    public A2AAgentContinuationToken(string taskId)
    {
        this.TaskId = taskId;
    }

    public string TaskId { get; set; }

    public static LongRunContinuationToken FromToken(ContinuationToken token)
    {
        if (token is LongRunContinuationToken longRunContinuationToken)
        {
            return longRunContinuationToken;
        }

        ... // Deserialization logic
    }
}

public class AgentRunOptions
{
    public ResponseContinuationToken? ContinuationToken { get; set; }
}

public class AgentRunResponse
{
    public ResponseContinuationToken? ContinuationToken { get; }
}
 
public class AgentRunResponseUpdate
{
    public ResponseContinuationToken? ContinuationToken { get; }
}

// Usage example
AgentRunResponse response = await agent.RunAsync("What is the capital of France?");

AgentRunOptions options = new() { ContinuationToken = response.ContinuationToken };

while (response.ContinuationToken is { } token)
{
    options.ContinuationToken = token;
    response = await agent.RunAsync([], options);
}

Console.WriteLine(response.Text);
```

### 4. Continuation Token and Agent Thread

There are two types of agent threads: server-managed and client-managed. The server-managed threads live server-side and are identified by a conversation identifier, and 
agents use the identifier to associate runs with the threads. The client-managed threads live client-side and are represented by a collection of chat messages that agents maintain
by adding user messages to them before sending the thread to the service and by adding the agent response back to the thread when received from the service.

When long-running operations are enabled and an agent is configured with tools, the initial run response may contain a tool call that needs to be invoked by the agent. If the agent runs
with a server-managed thread, the tool call will be captured as part of the conversation history server-side and follow-up runs will have access to it, and as a result the agent will invoke the tool.
However, if no thread is provided at the agent's initial run and a client-managed thread is provided for follow-up runs and the agent calls a tool, the tool call which the agent made 
at the initial run will not be added to the client-managed thread since the initial run was made with no thread, and as a result the agent will not be able to invoke the tool.

#### 4.1 Require Thread for Long-Running Operations

This option suggests that AI agents require a thread to be provided when long-running operations are enabled. If no thread is provided, the agent will throw an exception.

**Pro:** Ensures agent responses are always captured by client-managed threads when long-running operations are enabled, providing a consistent experience for callers.

**Con:** May be inconvenient for callers to always provide a thread when long-running operations are enabled.

#### 4.2 Don't Require Thread for Long-Running Operations

This option suggests that AI agents don't require a thread to be provided when long-running operations are enabled. According to this option, it's up to the caller to ensure that
the thread is provided with background operations consistently for all runs.

**Pro:** Provides more flexibility to callers by not enforcing thread requirements.

**Con:** May lead to an inconsistent experience for callers if they forget to provide the thread for initial or follow-up runs.

## Decision Outcome

### Long-Running Execution Support for Chat Clients
- **Methods**: Option 1.4 - Use existing `Get{Streaming}ResponseAsync` for common operations; individual interfaces for uncommon operations (e.g., `ICancelableChatClient`)
- **Enabling**: Option 2.1 - Execution mode per invocation via `ChatOptions.AllowLongRunningResponses`
- **Status/Result**: Option 3.2 - Single method to get both status and result
- **RunId/UpdateId**: Option 4.2 - As properties of `ChatResponse{Update}`
- **Model**: Option 6.1.5 - Custom continuation token type

### Long-Running Operations Support for AF Agents
- **Methods**: Option 1.1 - Use existing `Run{Streaming}Async` for common operations; new methods for uncommon operations
- **Enabling**: Option 2.1 - Execution mode per invocation via `AgentRunOptions.AllowLongRunningResponses`
- **Model**: Option 3.1 - Custom continuation token type
- **Thread Requirement**: Option 4.1 - Require thread for long-running operations

## Addendum 1: APIs of Agents Supporting Long-Running Execution
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
 
- Background Mode Disabled

  - Non-streaming API - returns the final result
     | Method Call                         | Status    | Result                          | Notes                               |
     |-------------------------------------|-----------|---------------------------------|-------------------------------------|
     | CreateResponseAsync(msgs, opts, ct) | Completed | The capital of France is Paris. |                                     |
     | GetResponseAsync(responseId, ct)    | Completed | The capital of France is Paris. | response is less than 5 minutes old |
     | GetResponseAsync(responseId, ct)    | Completed | The capital of France is Paris. | response is more than 5 minutes old |
     | GetResponseAsync(responseId, ct)    | Completed | The capital of France is Paris. | response is more than 12 hours old  |
  
     | Cancellation Method | Result                               |
     |---------------------|--------------------------------------|
     | CancelResponseAsync | Cannot cancel a synchronous response |

  - Streaming API - returns streaming updates callers can iterate over to get the result
     | Method Call                                  | Status     | Result                                                                           |
     |----------------------------------------------|------------|----------------------------------------------------------------------------------|
     | CreateResponseStreamingAsync(msgs, opts, ct) | -          | updates                                                                          |
     | Iterating over updates                       | InProgress | -                                                                                |
     | Iterating over updates                       | InProgress | -                                                                                |
     | Iterating over updates                       | InProgress | The                                                                              |
     | Iterating over updates                       | InProgress | capital                                                                          |
     | Iterating over updates                       | InProgress | ...                                                                              |
     | Iterating over updates                       | InProgress | Paris.                                                                           |
     | Iterating over updates                       | Completed  | The capital of France is Paris.                                                  |
     | GetStreamingResponseAsync(responseId, ct)    | -          | HTTP 400 - Response cannot be streamed, it was not created with background=true. |
  
     | Cancellation Method | Result                               |
     |---------------------|--------------------------------------|
     | CancelResponseAsync | Cannot cancel a synchronous response |
   
- Background Mode Enabled
  
  - Non-streaming API - returns queued response immediately and allow polling for the status and result
     | Method Call                         | Status    | Result                          | Notes                                      |
     |-------------------------------------|-----------|---------------------------------|--------------------------------------------|
     | CreateResponseAsync(msgs, opts, ct) | Queued    | responseId                      |                                            |
     | GetResponseAsync(responseId, ct)    | Queued    | -                               | if called before the response is completed |
     | GetResponseAsync(responseId, ct)    | Queued    | -                               | if called before the response is completed |
     | GetResponseAsync(responseId, ct)    | Completed | The capital of France is Paris. | response is less than 5 minutes old        |
     | GetResponseAsync(responseId, ct)    | Completed | The capital of France is Paris. | response is more than 5 minutes old        |
     | GetResponseAsync(responseId, ct)    | Completed | The capital of France is Paris. | response is more than 12 hours old         |

     The response started in background mode runs server-side until it completes, fails, or is cancelled. The client can poll for
     the status of the response using its Id. If the client polls before the response is completed, it will get the latest status of the response.
     If the client polls after the response is completed, it will get the completed response with the result.
  
     | Cancellation Method | Result    | Notes                                  |
     |---------------------|-----------|----------------------------------------|
     | CancelResponseAsync | Cancelled | if cancelled before response completed |
     | CancelResponseAsync | Completed | if cancelled after response completed  |
     | CancellationToken   | No effect | it just cancels the client side call   |

  - Streaming API - returns streaming updates callers can iterate over immediately or after dropping the stream and picking it up later
     | Method Call                                  | Status     | Result                                                                         | Notes                                     |
     |----------------------------------------------|------------|--------------------------------------------------------------------------------|-------------------------------------------|
     | CreateResponseStreamingAsync(msgs, opts, ct) | -          | updates                                                                        |                                           |
     | Iterating over updates                       | Queued     | -                                                                              |                                           |
     | Iterating over updates                       | Queued     | -                                                                              |                                           |
     | Iterating over updates                       | InProgress | -                                                                              |                                           |
     | Iterating over updates                       | InProgress | -                                                                              |                                           |
     | Iterating over updates                       | InProgress | The                                                                            |                                           |
     | Iterating over updates                       | InProgress | capital                                                                        |                                           |
     | Iterating over updates                       | InProgress | ...                                                                            |                                           |
     | Iterating over updates                       | InProgress | Paris.                                                                         |                                           |
     | Iterating over updates                       | Completed  | The capital of France is Paris.                                                |                                           |
     | GetStreamingResponseAsync(responseId, ct)    | -          | updates                                                                        | response is less than 5 minutes old       |
     | Iterating over updates                       | Queued     | -                                                                              |                                           |
     | ... 									        | ...        | ...                                                                            |                                           |
     | GetStreamingResponseAsync(responseId, ct)    | -          |  HTTP 400 - Response can no longer be streamed, it is more than 5 minutes old. | response is more than 5 minutes old       |
     | GetResponseAsync(responseId, ct)	            | Completed  | The capital of France is Paris.                                                | accessing response that can't be streamed |
  
     The streamed response that is not available after 5 minutes can be retrieved using the non-streaming API `GetResponseAsync`.
       
     | Cancellation Method | Result                             | Notes                                  |
     |---------------------|------------------------------------|----------------------------------------|
     | CancelResponseAsync | Canceled<sup>1</sup>               | if cancelled before response completed |
     | CancelResponseAsync | Cannot cancel a completed response | if cancelled after response completed  |
     | CancellationToken   | No effect                          | it just cancels the client side call   |

     <sup>1</sup> The CancelResponseAsync method returns `Canceled` status, but a subsequent call to GetResponseStreamingAsync returns 
     an enumerable that can be iterated over to get the rest of the response until it completes.
  
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
    GetRunStepAsync

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
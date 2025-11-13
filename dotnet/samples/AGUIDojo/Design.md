# Design for Blazor Agent UI
This document covers the design of the Microsoft.AspNetCore.Components.AI library for apps that interact with AI agents. Below we enumerate the general design patterns that we aim to provide in this area

## Scenario 1 - Include an agent on the UI

```html
<AgentBoundary Agent="@myAgent">
</AgentBoundary>
```

AgentBoundary is responsible for "connecting the UI to the agent.

It keeps track of the messages back and forth between the agent and the UI.

It provides an AgentBoundaryContext cascading value that other children component can use to:
* Listen for new messages
  * The context exposes an `IAsyncEnumerable<ChatMessage>` Messages stream of messages (including past messages and future messages, this is a "cold" enumerable)
  * The context exposes an `IAsyncEnumerable<IAsyncEnumerable<ChatResponseUpdate>>` stream of updates per turn.
    * The outer IEnumerable represents all the turns between the user and the LLM.
    * The inner IEnumerable represents the updates for the current run.
    * This is a "hot" enumerable, meaning that you don't get past updates, only new ones.
  * The context exposes a T State property that represents any state associated with the agent.
  * The context exposes an IAsyncEnumerable<T> stream that represents state updates if there is state attached to the Agent.
  * The context exposes a `SendAsync` method to trigger an interaction with the agent, which might include new messages as well as state.
  * The context exposes a CancellationToken tied to the lifetime of the AgentBoundary

AgentBoundary doesn't have any UI, it's all about managing the interaction with the agent. This gives users the freedom to implement other parts of their agentic UI as they see fit.

That said, we provide components to render a default input box as well as components to render the list of messages.

Here is a more complete example:
```html
<AgentBoundary Agent="@myAgent">
    <Messages />
    <AgentInput />
</AgentBoundary>
```

The snippet above will render the default Chat like UI that we are all used to seeing and using.

## Messages Component

The messages component is responsible for the bulk of functionality in rendering messages from the agent. It's responsible for subscribing to the AgentBoundaryContext update stream and making sure that messages are rendered as they arrive. It holds the list of messages in memory and re-renders as new messages arrive.

Our default Messages component supports customizing the way messages are rendered via templates. Users can define custom content templates to control how messages are rendered. These templates reflect the different content types that are available on Microsoft.Extensions.AI. There is a default template class for each content type and a general fallback template that can be used to provide a fallback for any unknown content.

Some templates can have additional parameters. For example, the DataContentTemplate can specify a mime type to filter on and only render data messages that match that mime type. Similarly, the ToolCallContentTemplate can specify a tool name to filter on.

The content templates provide a context object that includes two properties:
* Message: That gives access to the completed message (if available)
* Updates: That gives access to the list of updates being rendered for the current incoming message.

The Messages component provides a default rendering template for TextContent. Any other content type will just not be rendered unless the developer provides a custom template for it.

Here is a list of all the available content templates:

* CodeInterpreterToolCallTemplate
* CodeInterpreterToolResultTemplate
* DataTemplate
* ErrorTemplate
* FunctionCallTemplate
* FunctionResultTemplate
* FunctionApprovalRequestTemplate 
* FunctionApprovalResponseTemplate
* HostedFileTemplate
* HostedVectorStoreTemplate
* ImageGenerationToolCallTemplate
* ImageGenerationToolResultTemplate
* McpServerToolCallTemplate
* McpServerToolResultTemplate
* TextTemplate
* TextReasoningTemplate
* UriTemplate
* UsageTemplate
* UserInputRequestTemplate
* UserInputResponseTemplate

MessageModifiers can be used to modify the way messages are rendered. For example, a MessageModifier can be used to customize the "frame" around a message, so that ContentTemplates can focus on rendering the content itself. At the same time, MessageModifiers can be used to add additional UI elements around the message or provide overrides for specific AI contents.

All ContentTemplates and MessageModifiers extend a base class ContentTemplateBase or MessageModifierBase respectively. They expose a "When" parameter that receives the message and returns a boolean indicating whether the template/modifier should be applied to that message/update.

The MessageModifiers that exist by default are:
* UserMessageModifier
* SystemMessageModifier
* AssistantMessageModifier
* ToolMessageModifier

Internally the Messages component follows this algorithm to render messages:
1. For any given message: It first tries to match against an existing WellKnown MessageModifier (User, System, Assistant, Tool). If it matches a well known MessageModifier, it uses that one to render the message.
  - We do this to avoid having to iterate over all MessageModifiers for the most common cases.
  - Well known MessageModifiers take more precedence than custom message modifiers.
2. If no well known MessageModifier matches, it iterates over all custom MessageModifiers in the order they were defined and uses the first one that matches.
3. If no MessageModifier matches, it uses the DefaultMessageModifier to render the message.

4. We merge the list of default content renderers with the content renderers in the modifier (if applicable) and then we proceed to find the right content template for each content in the message:
  - For any given content in the message, we first try to match against well known ContentTemplates in the merged set.
    - We do this to avoid having to iterate over all ContentTemplates for the most common cases.
    - Well known ContentTemplates take more precedence than custom content templates.
  - If no well known ContentTemplate matches, we iterate over all custom ContentTemplates in the merged set in the order they were defined and use the first one that matches.
  - If no matching ContentTemplate is found, we don't render any content. 
  - If no content is rendered for a message, we skip rendering the message entirely.

By default we render each message inside a `div` with CSS classes that reflect the role of the message (user, system, assistant, tool) as well as whether or not the message is complete. This can be customized by providing custom MessageModifiers. The modifier context provides access to a RenderContents method that can be used to render the contents of the message using the content templates.

With this in mind, let's walk through some very common scenarios:

### Customizing messages based on role

```html
<AgentBoundary Agent="@myAgent">
    <Messages>
        <MessageModifiers>
            <UserMessageModifier>
                <div class="message user-message" style="background-color: lightblue; padding: 10px; border-radius: 5px; margin: 5px;">
                    @context.RenderContents()
                </div>
            </UserMessageModifier>
            <AssistantMessageModifier>
                <div class="message assistant-message" style="background-color: lightgreen; padding: 10px; border-radius: 5px; margin: 5px;">
                    @context.RenderContents()
                </div>
            </AssistantMessageModifier>
        </MessageModifiers>
    </Messages>
    <AgentInput />
</AgentBoundary>
```

### Rendering tool calls

```html
<AgentBoundary Agent="@myAgent">
    <Messages>
        <ContentTemplates>
            <ToolCallContentTemplate ToolName="get_weather">
                <Map Location="@context.GetArgument<string>("location")" />
            </ToolCallContentTemplate>
        </ContentTemplates>
    </Messages>
    <AgentInput />
</AgentBoundary>
```

### Rendering tool results
<!-- TODO: Consider an InvocationContext or similar capable of matching results to function calls -->
```html
<AgentBoundary Agent="@myAgent">
    <Messages>
        <ContentTemplates>
            <ToolResultContentTemplate ToolName="get_weather">
                <div class="weather-result">
                    Weather in @context.GetArgument<string>("location"): @context.GetArgument<string>("weather_description"), Temperature: @context.GetArgument<double>("temperature") °C
                </div>
            </ToolResultContentTemplate>
        </ContentTemplates>
    </Messages>
    <AgentInput />
</AgentBoundary>
```

### Rendering approvals

```html
<AgentBoundary Agent="@myAgent">
    <Messages>
        <ContentTemplates>
            <FunctionApprovalRequestTemplate>
                <div class="approval-request">
                    <p>Function: @context.FunctionName</p>
                    <p>Details: @context.Details</p>
                    <button @onclick="() => context.AgentContext.Approve(context.Request)">Approve</button>
                    <button @onclick="() => context.AgentContext.Reject(context.Request)">Reject</button>
                </div>
            </FunctionApprovalRequestTemplate>
        </ContentTemplates>
    </Messages>
    <AgentInput />
</AgentBoundary>
```

### Rendering images

```html
<AgentBoundary Agent="@myAgent">
    <Messages>
        <ContentTemplates>
            <ImageGenerationToolResultTemplate>
                <img src="@context.ImageUrl" alt="Generated Image" />
            </ImageGenerationToolResultTemplate>
        </ContentTemplates>
    </Messages>
    <AgentInput />
</AgentBoundary>
```

## Types

```csharp
// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.AI;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.AspNetCore.Components.AI;

// Main boundary component that connects UI to agent
public class AgentBoundary : IComponent
{
    [Parameter] public IAgent Agent { get; set; }
    [Parameter] public RenderFragment ChildContent { get; set; }
    
    public void Attach(RenderHandle renderHandle) => throw new NotImplementedException();
    public Task SetParametersAsync(ParameterView parameters) => throw new NotImplementedException();
}

// Non-generic context provided by AgentBoundary
public abstract class AgentBoundaryContext
{
    IAsyncEnumerable<ChatMessage> Messages { get; }
    IAsyncEnumerable<IAsyncEnumerable<ChatResponseUpdate>> UpdateStreams { get; }
    object GetState();
    IAsyncEnumerable<object> GetStateUpdates();
    Task SendAsync(object state, params Span<ChatMessage> newMessages);
    CancellationToken CancellationToken { get; }
    
    // Methods for approval scenarios
    Task Approve(FunctionApprovalRequest request);
    Task Reject(FunctionApprovalRequest request);
}

// Generic context with typed state
public abstract class AgentBoundaryContext<TState> : AgentBoundaryContext
{
    public abstract TState State { get; }
    public abstract IAsyncEnumerable<TState> StateUpdates { get; }
    public abstract Task SendAsync(TState state, params Span<ChatMessage> newMessages);
}

// Main messages display component
public class Messages : IComponent
{
    [Parameter] public RenderFragment MessageModifiers { get; set; }
    [Parameter] public RenderFragment ContentTemplates { get; set; }
    [CascadingParameter] public IAgentBoundaryContext AgentContext { get; set; }
    
    public void Attach(RenderHandle renderHandle) => throw new NotImplementedException();
    public Task SetParametersAsync(ParameterView parameters) => throw new NotImplementedException();
}

// Input component for user interactions
public class AgentInput : IComponent
{
    [CascadingParameter] public IAgentBoundaryContext AgentContext { get; set; }
    
    public void Attach(RenderHandle renderHandle) => throw new NotImplementedException();
    public Task SetParametersAsync(ParameterView parameters) => throw new NotImplementedException();
}

// Base classes for templates and modifiers
public abstract class MessageModifierBase : IComponent
{
    [Parameter] public Func<ChatMessage, bool> When { get; set; }
    [Parameter] public RenderFragment<MessageModifierContext> ChildContent { get; set; }
    
    public void Attach(RenderHandle renderHandle) => throw new NotImplementedException();
    public Task SetParametersAsync(ParameterView parameters) => throw new NotImplementedException();
}

public abstract class ContentTemplateBase : IComponent
{
    [Parameter] public Func<AIContent, bool> When { get; set; }
    [Parameter] public RenderFragment<ContentTemplateContext> ChildContent { get; set; }
    
    public void Attach(RenderHandle renderHandle) => throw new NotImplementedException();
    public Task SetParametersAsync(ParameterView parameters) => throw new NotImplementedException();
}

// Context types for templates
public class MessageModifierContext
{
    public ChatMessage Message { get; set; }
    public IEnumerable<ChatResponseUpdate> Updates { get; set; }
    public RenderFragment RenderContents() => default;
}

public class ContentTemplateContext
{
    public ChatMessage Message { get; set; }
    public IReadOnlyList<ChatResponseUpdate> Updates { get; set; }
    public IAgentBoundaryContext AgentContext { get; set; }
    public T GetArgument<T>(string name) => default;
}

// Specialized context for approval scenarios
public class FunctionApprovalContext : ContentTemplateContext
{
    public string FunctionName { get; set; }
    public string Details { get; set; }
    public FunctionApprovalRequest Request { get; set; }
}

// Message modifiers for different roles
public class UserMessageModifier : MessageModifierBase { }
public class SystemMessageModifier : MessageModifierBase { }
public class AssistantMessageModifier : MessageModifierBase { }
public class ToolMessageModifier : MessageModifierBase { }
public class DefaultMessageModifier : MessageModifierBase { }

// Content templates for different content types
public class TextTemplate : ContentTemplateBase { }

public class TextReasoningTemplate : ContentTemplateBase { }

public class DataTemplate : ContentTemplateBase 
{
    [Parameter] public string MimeType { get; set; }
}

public class ImageTemplate : ContentTemplateBase { }

public class UriTemplate : ContentTemplateBase { }

public class UsageTemplate : ContentTemplateBase { }

public class ErrorTemplate : ContentTemplateBase { }

public class HostedFileTemplate : ContentTemplateBase { }

public class HostedVectorStoreTemplate : ContentTemplateBase { }

// Function/Tool related templates
public class FunctionCallTemplate : ContentTemplateBase { }

public class FunctionResultTemplate : ContentTemplateBase { }

public class ToolCallContentTemplate : ContentTemplateBase 
{
    [Parameter] public string ToolName { get; set; }
}

public class ToolResultContentTemplate : ContentTemplateBase 
{
    [Parameter] public string ToolName { get; set; }
}

// Approval templates
public class FunctionApprovalRequestTemplate : ContentTemplateBase 
{
    [Parameter] public new RenderFragment<FunctionApprovalContext> ChildContent { get; set; }
}

public class FunctionApprovalResponseTemplate : ContentTemplateBase { }

// User input templates
public class UserInputRequestTemplate : ContentTemplateBase { }

public class UserInputResponseTemplate : ContentTemplateBase { }

// Specialized tool templates
public class CodeInterpreterToolCallTemplate : ContentTemplateBase { }

public class CodeInterpreterToolResultTemplate : ContentTemplateBase { }

public class ImageGenerationToolCallTemplate : ContentTemplateBase { }

public class ImageGenerationToolResultTemplate : ContentTemplateBase 
{
    public string ImageUrl => default;
}

public class McpServerToolCallTemplate : ContentTemplateBase { }

public class McpServerToolResultTemplate : ContentTemplateBase { }

// Supporting types
public class FunctionApprovalRequest
{
    public string FunctionName { get; set; }
    public IDictionary<string, object> Arguments { get; set; }
}

// Agent interface (assumed from Microsoft.Extensions.AI)
public interface IAgent
{
    // Agent interface members would be defined in Microsoft.Extensions.AI
}
```
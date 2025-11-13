// Copyright (c) Microsoft. All rights reserved.

using Microsoft.AspNetCore.Components.Rendering;
using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

#pragma warning disable CA1812 // Internal class is apparently never instantiated
internal sealed partial class MessageList : IComponent, IDisposable
#pragma warning restore CA1812 // Internal class is apparently never instantiated
{
    private RenderHandle _renderHandle;
    private MessageSubscription _messageSubscription;
    private ResponseUpdateSubscription _responseSubscription;

    [CascadingParameter] public MessageListContext MessageListContext { get; set; } = default!;

    public void Attach(RenderHandle renderHandle)
    {
        this._renderHandle = renderHandle;
    }

    public Task SetParametersAsync(ParameterView parameters)
    {
        var previousContext = this.MessageListContext;
        parameters.SetParameterProperties(this);

        if (previousContext != null && this.MessageListContext != previousContext)
        {
            throw new InvalidOperationException(
                $"{nameof(MessageList)} does not support changing the {nameof(this.MessageListContext)} once it has been set.");
        }

        // Subscribe to message updates and response updates for streaming
        this._messageSubscription = this.MessageListContext.AgentBoundaryContext.SubscribeToMessageChanges(this.ProcessUpdate);
        this._responseSubscription = this.MessageListContext.AgentBoundaryContext.SubscribeToResponseUpdates(this.ProcessUpdate);
        Log.MessageListAttached(this.MessageListContext.AgentBoundaryContext.Logger);
        Log.MessageListSubscribed(this.MessageListContext.AgentBoundaryContext.Logger);

        // Initial render. This component will only render once since the only parameter is a cascading parameter and it's fixed.
        this._renderHandle.Render(this.Render);

        return Task.CompletedTask;
    }

    private void ProcessUpdate()
    {
        // Scan all messages for function calls and results to track invocations.
        // This allows us to associate results with their calls when results arrive.
        foreach (var message in this.MessageListContext.AgentBoundaryContext.CompletedMessages)
        {
            this.ProcessMessageContents(message);
        }

        foreach (var message in this.MessageListContext.AgentBoundaryContext.PendingMessages)
        {
            this.ProcessMessageContents(message);
        }

        this._renderHandle.Render(this.Render);
    }

    private void ProcessMessageContents(ChatMessage message)
    {
        foreach (var content in message.Contents)
        {
            if (content is FunctionCallContent call)
            {
                this.MessageListContext.GetOrCreateInvocation(call);
            }
            else if (content is FunctionResultContent result)
            {
                this.MessageListContext.AssociateResult(result);
            }
        }
    }

    public void Render(RenderTreeBuilder builder)
    {
        Log.MessageListRendering(
            this.MessageListContext.AgentBoundaryContext.Logger,
            this.MessageListContext.AgentBoundaryContext.CompletedMessages.Count,
            this.MessageListContext.AgentBoundaryContext.PendingMessages.Count);

        // Track all render keys to detect duplicates
        var allRenderKeys = new HashSet<string?>();

        foreach (var message in this.MessageListContext.AgentBoundaryContext.CompletedMessages)
        {
            var renderKey = GetUniqueRenderKey(message);

            Log.RenderingCompletedMessage(
                this.MessageListContext.AgentBoundaryContext.Logger,
                message.MessageId,
                renderKey,
                message.Role.Value,
                message.Contents.Count);

            if (renderKey != null && !allRenderKeys.Add(renderKey))
            {
                Log.DuplicateRenderKeyDetected(
                    this.MessageListContext.AgentBoundaryContext.Logger,
                    renderKey,
                    "completed");
            }

            // Calling GetTemplate will stop template collection on the first message if it
            // was still ongoing.
            builder.OpenComponent<ContentBlock>(0);
            builder.SetKey(renderKey);
            builder.AddComponentParameter(1, "ChildContent", this.MessageListContext.GetTemplate(message));
            builder.CloseComponent();
        }

        foreach (var message in this.MessageListContext.AgentBoundaryContext.PendingMessages)
        {
            var renderKey = GetUniqueRenderKey(message);

            Log.RenderingPendingMessage(
                this.MessageListContext.AgentBoundaryContext.Logger,
                message.MessageId,
                renderKey,
                message.Role.Value,
                message.Contents.Count);

            if (renderKey != null && !allRenderKeys.Add(renderKey))
            {
                Log.DuplicateRenderKeyDetected(
                    this.MessageListContext.AgentBoundaryContext.Logger,
                    renderKey,
                    "pending");
            }

            builder.OpenComponent<ContentBlock>(1);
            builder.SetKey(renderKey);
            builder.AddComponentParameter(1, "ChildContent", this.MessageListContext.GetTemplate(message));
            builder.CloseComponent();
        }
    }

    /// <summary>
    /// Gets a unique render key for a message.
    /// For tool result messages (role=tool), we use MessageId + CallId to ensure uniqueness
    /// because the AGUI protocol may reuse MessageId for multiple tool results in the same batch.
    /// </summary>
    private static string? GetUniqueRenderKey(ChatMessage message)
    {
        // For tool result messages, combine MessageId with CallId to ensure uniqueness
        // This works around a bug in the AGUI protocol where multiple tool results
        // can share the same MessageId when processed in the same update batch.
        if (message.Role == ChatRole.Tool)
        {
            var resultContent = message.Contents.OfType<FunctionResultContent>().FirstOrDefault();
            if (resultContent != null && !string.IsNullOrEmpty(resultContent.CallId))
            {
                return $"{message.MessageId}_{resultContent.CallId}";
            }
        }

        return message.MessageId;
    }

    public void Dispose()
    {
        Log.MessageListDisposed(this.MessageListContext.AgentBoundaryContext.Logger);
        ((IDisposable)this._messageSubscription).Dispose();
        ((IDisposable)this._responseSubscription).Dispose();
    }

    private static partial class Log
    {
        [LoggerMessage(Level = LogLevel.Debug, Message = "MessageList attached to render handle")]
        public static partial void MessageListAttached(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "MessageList subscribed to message changes")]
        public static partial void MessageListSubscribed(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "MessageList rendering, completed: {CompletedCount}, pending: {PendingCount}")]
        public static partial void MessageListRendering(ILogger logger, int completedCount, int pendingCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Rendering completed message: MessageId={MessageId}, RenderKey={RenderKey}, Role={Role}, ContentCount={ContentCount}")]
        public static partial void RenderingCompletedMessage(ILogger logger, string? messageId, string? renderKey, string role, int contentCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Rendering pending message: MessageId={MessageId}, RenderKey={RenderKey}, Role={Role}, ContentCount={ContentCount}")]
        public static partial void RenderingPendingMessage(ILogger logger, string? messageId, string? renderKey, string role, int contentCount);

        [LoggerMessage(Level = LogLevel.Warning, Message = "DUPLICATE RenderKey detected: {RenderKey} in {Location} messages")]
        public static partial void DuplicateRenderKeyDetected(ILogger logger, string renderKey, string location);

        [LoggerMessage(Level = LogLevel.Debug, Message = "MessageList disposed")]
        public static partial void MessageListDisposed(ILogger logger);
    }
}

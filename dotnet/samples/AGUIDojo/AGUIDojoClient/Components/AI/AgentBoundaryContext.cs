// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Microsoft.AspNetCore.Components.AI;

public sealed partial class AgentBoundaryContext<TState> : IAgentBoundaryContext, IDisposable
{
    private readonly AIAgent _agent;
    private readonly AgentThread _thread;
    private readonly CancellationTokenSource _cancellationTokenSource;
    private readonly ILogger _logger;
    private readonly List<ChatMessage> _messages = [];
    private readonly List<ChatMessage> _pendingMessages = [];
    private readonly List<Action> _messageChangeSubscribers = [];
    private readonly List<Action> _responseUpdateSubscribers = [];
    private readonly List<AITool> _tools = [];
    private readonly Dictionary<string, TaskCompletionSource<object>> _pendingResponses = [];

    public CancellationToken CancellationToken => this._cancellationTokenSource.Token;

    public IReadOnlyList<ChatMessage> CompletedMessages => this._messages.AsReadOnly();

    public TState? CurrentState { get; set; }

    public IReadOnlyList<ChatMessage> PendingMessages => this._pendingMessages.AsReadOnly();

    public ChatMessage? CurrentMessage { get; private set; }

    public ChatResponseUpdate? CurrentUpdate { get; private set; }

    ILogger IAgentBoundaryContext.Logger => this._logger;

    public AgentBoundaryContext(AIAgent agent, AgentThread thread, ILogger logger)
    {
        this._agent = agent;
        this._thread = thread;
        this._cancellationTokenSource = new CancellationTokenSource();
        this._logger = logger;
        Log.AgentBoundaryContextCreated(this._logger);
    }

    /// <summary>
    /// Registers a client-side tool that will be passed to the agent during invocation.
    /// These tools are sent to the server via ChatClientAgentRunOptions.ChatOptions.Tools.
    /// </summary>
    public void RegisterTool(AITool tool)
    {
        ArgumentNullException.ThrowIfNull(tool);
        this._tools.Add(tool);
        Log.ToolRegistered(this._logger, tool.Name);
    }

    /// <summary>
    /// Registers multiple client-side tools that will be passed to the agent during invocation.
    /// </summary>
    public void RegisterTools(params AITool[] tools)
    {
        foreach (var tool in tools)
        {
            this.RegisterTool(tool);
        }
    }

    /// <summary>
    /// Creates a pending response for the given key and returns a task that completes when ProvideResponse is called.
    /// Used by frontend tools to wait for user input from UI components.
    /// </summary>
    /// <param name="key">A unique key to identify this pending response (e.g., function call ID).</param>
    /// <returns>A task that completes with the response object when ProvideResponse is called.</returns>
    public Task<object> WaitForResponse(string key)
    {
        var tcs = new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
        this._pendingResponses[key] = tcs;
        Log.WaitForResponseStarted(this._logger, key);
        return tcs.Task;
    }

    /// <summary>
    /// Provides a response for a pending request, completing the task returned by WaitForResponse.
    /// Called by UI components when user interaction is complete.
    /// </summary>
    /// <param name="key">The key used when calling WaitForResponse.</param>
    /// <param name="response">The response object to return.</param>
    /// <returns>True if the response was provided successfully, false if no pending request was found.</returns>
    public bool ProvideResponse(string key, object response)
    {
        if (this._pendingResponses.TryGetValue(key, out var tcs))
        {
            this._pendingResponses.Remove(key);
            tcs.TrySetResult(response);
            Log.ResponseProvided(this._logger, key);
            return true;
        }

        Log.ResponseNotFound(this._logger, key);
        return false;
    }

    public void Dispose()
    {
        Log.AgentBoundaryContextDisposed(this._logger);
        this._cancellationTokenSource.Cancel();
        this._cancellationTokenSource.Dispose();
        GC.SuppressFinalize(this);
    }

    public async Task SendAsync(params ChatMessage[] userMessages)
    {
        Log.SendAsyncStarted(this._logger, userMessages.Length);

        // This starts a new turn. Once completed, we will add the new messages to the conversation.
        this._pendingMessages.Clear();
        this._pendingMessages.AddRange(userMessages);

        // User messages added, notify subscribers.
        this.TriggerMessageChanges();

        // Build run options with registered tools if any
        AgentRunOptions? options = null;
        if (this._tools.Count > 0)
        {
            options = new ChatClientAgentRunOptions(new ChatOptions
            {
                Tools = [.. this._tools]
            });
            Log.RunningWithTools(this._logger, this._tools.Count);
        }

        // Start a turn. Collect all updates as we stream them.
        await foreach (var update in this._agent.RunStreamingAsync(
            userMessages,
            this._thread,
            options,
            this._cancellationTokenSource.Token))
        {
            var chatUpdate = update.AsChatResponseUpdate();

            this.CurrentUpdate = chatUpdate;
            Log.ChatResponseUpdateReceived(this._logger);

            // Notify subscribers of the new update, this always happens before a new message is created/updated.
            this.TriggerChatResponseUpdate();

            // This creates or adds a new message to the pending messages as needed.
            var isNewMessage = MessageHelpers.ProcessUpdate(chatUpdate, this._pendingMessages, this._logger);
            if (isNewMessage)
            {
                Log.NewMessageCreated(this._logger, this._pendingMessages.Count);
                this.CurrentMessage = this._pendingMessages[this._pendingMessages.Count - 1];

                // Finalize the previous message's content if we have 2 or more messages now.
                if (this._pendingMessages.Count > userMessages.Length + 1)
                {
                    MessageHelpers.CoalesceContent(this._pendingMessages[this._pendingMessages.Count - 2].Contents);
                }

                // Notify subscribers of new message
                this.TriggerMessageChanges();
            }
        }

        // Process any remaining updates to finalize the last message.
        if (this._pendingMessages.Count > userMessages.Length)
        {
            MessageHelpers.CoalesceContent(this._pendingMessages[this._pendingMessages.Count - 1].Contents);
        }

        // Add the new messages to the conversation
        this._messages.AddRange(this._pendingMessages);

        // Finish the turn
        this._pendingMessages.Clear();
        this.CurrentMessage = null;
        this.CurrentUpdate = null;

        // Notify subscribers
        this.TriggerChatResponseUpdate();
        this.TriggerMessageChanges();

        Log.SendAsyncCompleted(this._logger, this._messages.Count);
    }

    private void TriggerChatResponseUpdate()
    {
        Log.ResponseUpdateSubscribersNotified(this._logger, this._responseUpdateSubscribers.Count);
        // Iterate backwards to avoid issues if subscribers are removed during iteration
        for (var i = this._responseUpdateSubscribers.Count - 1; i >= 0; i--)
        {
            this._responseUpdateSubscribers[i]();
        }
    }

    private void TriggerMessageChanges()
    {
        Log.MessageChangeSubscribersNotified(this._logger, this._messageChangeSubscribers.Count);
        // Iterate backwards to avoid issues if subscribers are removed during iteration
        for (var i = this._messageChangeSubscribers.Count - 1; i >= 0; i--)
        {
            this._messageChangeSubscribers[i]();
        }
    }

    public MessageSubscription SubscribeToMessageChanges(Action onNewMessage)
    {
        return new MessageSubscription(this._messageChangeSubscribers, onNewMessage);
    }

    public ResponseUpdateSubscription SubscribeToResponseUpdates(Action onChatResponse)
    {
        return new ResponseUpdateSubscription(this._responseUpdateSubscribers, onChatResponse);
    }

    private static partial class Log
    {
        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentBoundaryContext created for thread")]
        public static partial void AgentBoundaryContextCreated(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "AgentBoundaryContext disposed")]
        public static partial void AgentBoundaryContextDisposed(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "SendAsync started with {MessageCount} user message(s)")]
        public static partial void SendAsyncStarted(ILogger logger, int messageCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "SendAsync completed, total messages: {TotalMessages}")]
        public static partial void SendAsyncCompleted(ILogger logger, int totalMessages);

        [LoggerMessage(Level = LogLevel.Debug, Message = "New message created during streaming, pending count: {PendingCount}")]
        public static partial void NewMessageCreated(ILogger logger, int pendingCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Chat response update received")]
        public static partial void ChatResponseUpdateReceived(ILogger logger);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Message change subscribers notified, subscriber count: {SubscriberCount}")]
        public static partial void MessageChangeSubscribersNotified(ILogger logger, int subscriberCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Response update subscribers notified, subscriber count: {SubscriberCount}")]
        public static partial void ResponseUpdateSubscribersNotified(ILogger logger, int subscriberCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Tool registered: {ToolName}")]
        public static partial void ToolRegistered(ILogger logger, string toolName);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Running with {ToolCount} registered tool(s)")]
        public static partial void RunningWithTools(ILogger logger, int toolCount);

        [LoggerMessage(Level = LogLevel.Debug, Message = "WaitForResponse started for key: {Key}")]
        public static partial void WaitForResponseStarted(ILogger logger, string key);

        [LoggerMessage(Level = LogLevel.Debug, Message = "Response provided for key: {Key}")]
        public static partial void ResponseProvided(ILogger logger, string key);

        [LoggerMessage(Level = LogLevel.Warning, Message = "No pending response found for key: {Key}")]
        public static partial void ResponseNotFound(ILogger logger, string key);
    }
}

public interface IAgentBoundaryContext
{
    // Push new messages to the agent
    Task SendAsync(params ChatMessage[] userMessages);

    // All message interactions from previous turns
    IReadOnlyList<ChatMessage> CompletedMessages { get; }

    // All message interactions from the current turn. These represent completed messages only.
    IReadOnlyList<ChatMessage> PendingMessages { get; }

    // The current message being processed by the agent.
    ChatMessage? CurrentMessage { get; }

    ChatResponseUpdate? CurrentUpdate { get; }

    ILogger Logger { get; }

    // Triggered any time there is a change on a message.
    MessageSubscription SubscribeToMessageChanges(Action onNewMessage);

    ResponseUpdateSubscription SubscribeToResponseUpdates(Action onChatResponse);

    CancellationToken CancellationToken { get; }

    /// <summary>
    /// Registers a client-side tool that will be passed to the agent during invocation.
    /// </summary>
    void RegisterTool(AITool tool);

    /// <summary>
    /// Registers multiple client-side tools that will be passed to the agent during invocation.
    /// </summary>
    void RegisterTools(params AITool[] tools);

    /// <summary>
    /// Creates a pending response for the given key and returns a task that completes when ProvideResponse is called.
    /// Used by frontend tools to wait for user input from UI components.
    /// </summary>
    /// <param name="key">A unique key to identify this pending response (e.g., function call ID).</param>
    /// <returns>A task that completes with the response object when ProvideResponse is called.</returns>
    Task<object> WaitForResponse(string key);

    /// <summary>
    /// Provides a response for a pending request, completing the task returned by WaitForResponse.
    /// Called by UI components when user interaction is complete.
    /// </summary>
    /// <param name="key">The key used when calling WaitForResponse.</param>
    /// <param name="response">The response object to return.</param>
    /// <returns>True if the response was provided successfully, false if no pending request was found.</returns>
    bool ProvideResponse(string key, object response);
}

public readonly struct MessageSubscription : IDisposable, IEquatable<MessageSubscription>
{
    internal readonly List<Action> _subscribers;
    internal readonly Action _subscription;

    internal MessageSubscription(List<Action> subscribers, Action subscription)
    {
        this._subscribers = subscribers;
        this._subscription = subscription;
        this._subscribers.Add(this._subscription);
    }

    public void Dispose() => this._subscribers.Remove(this._subscription);

    public override bool Equals(object? obj)
    {
        return obj is MessageSubscription subscription && this.Equals(subscription);
    }

    public bool Equals(MessageSubscription other)
    {
        return EqualityComparer<List<Action>>.Default.Equals(this._subscribers, other._subscribers) &&
               EqualityComparer<Action>.Default.Equals(this._subscription, other._subscription);
    }

    public override int GetHashCode()
    {
        return HashCode.Combine(this._subscribers, this._subscription);
    }

    public static bool operator ==(MessageSubscription left, MessageSubscription right)
    {
        return left.Equals(right);
    }

    public static bool operator !=(MessageSubscription left, MessageSubscription right)
    {
        return !(left == right);
    }
}

public readonly struct ResponseUpdateSubscription : IDisposable, IEquatable<ResponseUpdateSubscription>
{
    private readonly List<Action> _subscribers;
    private readonly Action _subscription;

    public ResponseUpdateSubscription(List<Action> subscribers, Action subscription)
    {
        this._subscribers = subscribers;
        this._subscription = subscription;
        this._subscribers.Add(this._subscription);
    }

    public void Dispose() => this._subscribers.Remove(this._subscription);

    public override bool Equals(object? obj)
    {
        return obj is ResponseUpdateSubscription subscription && this.Equals(subscription);
    }

    public bool Equals(ResponseUpdateSubscription other)
    {
        return EqualityComparer<List<Action>>.Default.Equals(this._subscribers, other._subscribers) &&
               EqualityComparer<Action>.Default.Equals(this._subscription, other._subscription);
    }

    public override int GetHashCode()
    {
        return HashCode.Combine(this._subscribers, this._subscription);
    }

    public static bool operator ==(ResponseUpdateSubscription left, ResponseUpdateSubscription right)
    {
        return left.Equals(right);
    }

    public static bool operator !=(ResponseUpdateSubscription left, ResponseUpdateSubscription right)
    {
        return !(left == right);
    }
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Base class for multi-agent agent orchestration patterns.
/// </summary>
public abstract partial class OrchestratingAgent : AIAgent
{
    /// <summary>Key used to persist state with the runtime.</summary>
    private const string StateKey = "State";

    /// <summary>
    /// Initializes a new instance of the <see cref="OrchestratingAgent"/> class.
    /// </summary>
    /// <param name="agents">Specifies the agents participating in this orchestration.</param>
    protected OrchestratingAgent(IReadOnlyList<AIAgent> agents)
    {
        _ = Throw.IfNullOrEmpty(agents);

        this.Agents = agents;
    }

    /// <summary>
    /// Gets the list of member targets involved in the orchestration.
    /// </summary>
    protected IReadOnlyList<AIAgent> Agents { get; }

    /// <summary>Gets the serializer options to use by the orchestration.</summary>
    public JsonSerializerOptions? SerializerOptions { get; set; }

    /// <summary>
    /// Gets the associated logger.
    /// </summary>
    public ILoggerFactory LoggerFactory { get; set; } = NullLoggerFactory.Instance;

    /// <summary>
    /// Optional callback that is invoked for every agent response.
    /// </summary>
    public Func<IEnumerable<ChatMessage>, ValueTask>? ResponseCallback { get; set; }

    /// <summary>
    /// Optional callback that is invoked for every agent update.
    /// </summary>
    public Func<AgentRunResponseUpdate, ValueTask>? StreamingResponseCallback { get; set; }

    /// <inheritdoc />
    public sealed override async Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        if (thread is not null)
        {
            if (thread is not IMessagesRetrievableThread retrievableThread)
            {
                throw new InvalidOperationException($"The thread type '{thread.GetType().Name}' is not supported by this agent. Use {nameof(GetNewThread)} to create a thread when needed.");
            }

            List<ChatMessage> messagesList = [];
            await foreach (var threadMessage in retrievableThread.GetMessagesAsync(cancellationToken).ConfigureAwait(false))
            {
                messagesList.Add(threadMessage);
            }
            messagesList.AddRange(messages);
            messages = messagesList;
        }

        var orchestrationResult = await this.RunAsync(messages, options, runtime: null, cancellationToken).ConfigureAwait(false);
        return await orchestrationResult.Task.ConfigureAwait(false);
    }

    /// <inheritdoc />
    public sealed override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // TODO: There should be a RunAsync overload that returns an OrchestratingAgentStreamingResponse, which this then delegates to.

        var response = await this.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);
        foreach (var update in response.ToAgentRunResponseUpdates())
        {
            yield return update;
        }
    }

    /// <inheritdoc />
    public sealed override AgentThread GetNewThread() => new ChatClientAgentThread();

    /// <summary>
    /// Initiates processing of the orchestration.
    /// </summary>
    /// <param name="messages">The input message.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="runtime">The runtime associated with the orchestration.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public async ValueTask<OrchestratingAgentResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentRunOptions? options = null,
        IActorRuntimeContext? runtime = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages, nameof(messages));
        cancellationToken.ThrowIfCancellationRequested();

        ILogger logger = this.LoggerFactory.CreateLogger(this.GetType().Name);

        OrchestratingAgentContext context = new()
        {
            OrchestratingAgent = this,
            Runtime = runtime,
            Options = options,
            Logger = logger,
        };

        LogOrchestrationInvoked(logger, this.DisplayName, context.Id);

        CancellationTokenSource cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cancellationToken = cts.Token;

        JsonElement? checkpoint = await this.ReadCheckpointAsync(context, cancellationToken).ConfigureAwait(false);
        Task<AgentRunResponse> completion = checkpoint is null ?
            this.RunCoreAsync(messages, context, cancellationToken) :
            this.ResumeCoreAsync(checkpoint.Value, context, cancellationToken);

        if (logger.IsEnabled(LogLevel.Trace))
        {
            _ = LogCompletionAsync(logger, context, completion);
        }

        return new OrchestratingAgentResponse(context, completion, cts, logger);
    }

    /// <summary>
    /// Initiates processing of the orchestration.
    /// </summary>
    /// <param name="messages">The input message.</param>
    /// <param name="context">The context for this operation.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    protected abstract Task<AgentRunResponse> RunCoreAsync(IReadOnlyCollection<ChatMessage> messages, OrchestratingAgentContext context, CancellationToken cancellationToken);

    /// <summary>
    /// Resumes processing of the orchestration.
    /// </summary>
    /// <param name="checkpointState">The last checkpoint state available from which to resume the operation.</param>
    /// <param name="context">The context for this operation.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    protected abstract Task<AgentRunResponse> ResumeCoreAsync(JsonElement checkpointState, OrchestratingAgentContext context, CancellationToken cancellationToken);

    /// <summary>
    /// Runs the agent with input messages and respond with both streamed and regular messages.
    /// </summary>
    /// <param name="agent">The agent being run</param>
    /// <param name="context">The associated orchestration context for this run.</param>
    /// <param name="input">The list of chat messages to send.</param>
    /// <param name="options">Options to use when invoking the agent.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A task that returns the response <see cref="ChatMessage"/>.</returns>
    protected static async ValueTask<AgentRunResponse> RunAsync(AIAgent agent, OrchestratingAgentContext context, IReadOnlyCollection<ChatMessage> input, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        // Utilize streaming iff a streaming callback is provided; otherwise, use the non-streaming API.
        AgentRunResponse response;
        if (context.OrchestratingAgent?.StreamingResponseCallback is { } streamingCallback)
        {
            // For streaming, enumerate all the updates, invoking the callback for each, and storing them all.
            // Then convert them all into a single response instance.
            List<AgentRunResponseUpdate> updates = [];

            await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(input, options: options ?? context.Options, cancellationToken: cancellationToken).ConfigureAwait(false))
            {
                updates.Add(update);
                await streamingCallback(update).ConfigureAwait(false);
            }

            response = updates.ToAgentRunResponse();
        }
        else
        {
            // For non-streaming, just invoke the non-streaming method and get back the response.
            response = await agent.RunAsync(input, options: options ?? context.Options, cancellationToken: cancellationToken).ConfigureAwait(false);
        }

        // Regardless of whether we invoked streaming callbacks for individual updates, invoke the non-streaming callback with the final response instance.
        // This can be used as an indication of completeness if someone otherwise only cares about the streaming updates.
        if (context.OrchestratingAgent?.ResponseCallback is { } responseCallback)
        {
            await responseCallback.Invoke(response.Messages).ConfigureAwait(false);
        }

        return response;
    }

    /// <inheritdoc />
    protected sealed override TThreadType ValidateOrCreateThreadType<TThreadType>(AgentThread? thread, Func<TThreadType> constructThread) =>
        base.ValidateOrCreateThreadType(thread, constructThread);

    /// <summary>Writes the specified checkpoint state to the runtime.</summary>
    /// <param name="state">The state to persist.</param>
    /// <param name="context">The context for the orchestrating operation.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A Task that completes when the asynchronous operation quiesces.</returns>
    protected async Task WriteCheckpointAsync(JsonElement state, OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(context);

        if (context.Runtime is not null)
        {
            while (true)
            {
                var response = await context.Runtime.WriteAsync(
                    new ActorWriteOperationBatch(context.ETag ?? "", [new SetValueOperation(StateKey, state)]),
                    cancellationToken).ConfigureAwait(false);

                if (response.Success)
                {
                    break;
                }

                // If the write failed, there was a concurrency conflict where someone else updated the state.
                // But we don't actually care about consistency between the previous checkpoint and the current one,
                // so we just retry the write with the new etag.
                context.ETag = response.ETag;
            }
        }
    }

    /// <summary>Read checkpoint information, if it exists, for the specified context.</summary>
    /// <param name="context">The context for the orchestrating operation.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>The loaded state, or null if it doesn't exist.</returns>
    protected async ValueTask<JsonElement?> ReadCheckpointAsync(OrchestratingAgentContext context, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(context);

        if (context.Runtime is not null)
        {
            ReadResponse response = await context.Runtime.ReadAsync(
                new ActorReadOperationBatch([new GetValueOperation(StateKey)]),
                cancellationToken).ConfigureAwait(false);

            context.ETag = response.ETag;

            if (response.Results is { } results &&
                results[results.Count - 1] is GetValueResult { Value: not null } getValueResult)
            {
                return getValueResult.Value.Value;
            }
        }

        return default;
    }

    [LoggerMessage(Level = LogLevel.Trace, Message = "{Orchestration} started ('{Id}')")]
    private static partial void LogOrchestrationInvoked(ILogger logger, string orchestration, string id);

    [LoggerMessage(Level = LogLevel.Trace, Message = "{Orchestration} completed ('{Id}'). Result: '{Result}'")]
    private static partial void LogOrchestrationResult(ILogger logger, string orchestration, string id, string result);

    [LoggerMessage(Level = LogLevel.Trace, Message = "{Orchestration} cancellation requested ('{Id}')")]
    internal static partial void LogOrchestrationCancellationRequested(ILogger logger, string orchestration, string id);

    [LoggerMessage(Level = LogLevel.Trace, Message = "{Orchestration} failed ('{Id}')")]
    private static partial void LogOrchestrationFailure(ILogger logger, string orchestration, string id, Exception error);

    [LoggerMessage(Level = LogLevel.Trace, Message = "{Orchestration} invoking agent '{Agent}' ('{Id}')")]
    private static partial void LogOrchestrationSubagentRunning(ILogger logger, string orchestration, string id, string agent);

    [LoggerMessage(Level = LogLevel.Trace, Message = "{Orchestration} completed agent '{Agent}' ('{Id}')")]
    private static partial void LogOrchestrationSubagentCompleted(ILogger logger, string orchestration, string id, string agent);

    private protected void LogOrchestrationSubagentRunning(OrchestratingAgentContext context, AIAgent agent) =>
        LogOrchestrationSubagentRunning(context.Logger, context.ToString(), context.Id, agent.DisplayName);

    private protected void LogOrchestrationSubagentCompleted(OrchestratingAgentContext context, AIAgent agent) =>
        LogOrchestrationSubagentCompleted(context.Logger, context.ToString(), context.Id, agent.DisplayName);

    private static async Task LogCompletionAsync(ILogger logger, OrchestratingAgentContext context, Task<AgentRunResponse> completion)
    {
        try
        {
            AgentRunResponse result = await completion.ConfigureAwait(false);

            if (logger.IsEnabled(LogLevel.Trace))
            {
                JsonSerializerOptions jso = context.OrchestratingAgent?.SerializerOptions ?? AgentAbstractionsJsonUtilities.DefaultOptions;
                LogOrchestrationResult(logger, context.ToString(), context.Id, JsonSerializer.Serialize(result, jso.GetTypeInfo(typeof(AgentRunResponse))));
            }
        }
        catch (Exception ex)
        {
            LogOrchestrationFailure(logger, context.ToString(), context.Id, ex);
        }
    }
}

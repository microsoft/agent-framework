// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides extension methods for attaching A2A (Agent2Agent) messaging capabilities to an <see cref="AIAgent"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class AIAgentExtensions
{
    // Metadata key used to store continuation tokens for long-running background operations
    // in the AgentTask.Metadata dictionary, persisted by the task store.
    private const string ContinuationTokenMetadataKey = "__a2a__continuationToken";

    /// <summary>
    /// Attaches A2A (Agent2Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging. New instance will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <param name="agentSessionStore">The store to store session contents and metadata.</param>
    /// <param name="runMode">Controls the response behavior of the agent run.</param>
    /// <param name="jsonSerializerOptions">Optional <see cref="JsonSerializerOptions"/> for serializing and deserializing continuation tokens. Use this when the agent's continuation token contains custom types not registered in the default options. Falls back to <see cref="A2AHostingJsonUtilities.DefaultOptions"/> if not provided.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentSessionStore? agentSessionStore = null,
        AgentRunMode? runMode = null,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(agent.Name);

        runMode ??= AgentRunMode.DisallowBackground;

        var hostAgent = new AIHostAgent(
            innerAgent: agent,
            sessionStore: agentSessionStore ?? new NoopAgentSessionStore());

        taskManager ??= new TaskManager();

        // Resolve the JSON serializer options for continuation token serialization. May be custom for the user's agent.
        JsonSerializerOptions continuationTokenJsonOptions = jsonSerializerOptions ?? A2AHostingJsonUtilities.DefaultOptions;

        // OnMessageReceived handles both message-only and task-based flows.
        // The A2A SDK prioritizes OnMessageReceived over OnTaskCreated when both are set,
        // so we consolidate all initial message handling here and return either
        // an AgentMessage or AgentTask depending on the agent response.
        // When the agent returns a ContinuationToken (long-running operation), a task is
        // created for stateful tracking. Otherwise a lightweight AgentMessage is returned.
        // See https://github.com/a2aproject/a2a-dotnet/issues/275
        taskManager.OnMessageReceived += (p, ct) => OnMessageReceivedAsync(p, hostAgent, runMode, taskManager, continuationTokenJsonOptions, ct);

        // Task flow for subsequent updates and cancellations
        taskManager.OnTaskUpdated += (t, ct) => OnTaskUpdatedAsync(t, hostAgent, taskManager, continuationTokenJsonOptions, ct);
        taskManager.OnTaskCancelled += OnTaskCancelledAsync;

        return taskManager;
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="agentCard">The agent card to return on query.</param>
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging. New instance will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <param name="agentSessionStore">The store to store session contents and metadata.</param>
    /// <param name="runMode">Controls the response behavior of the agent run.</param>
    /// <param name="jsonSerializerOptions">Optional <see cref="JsonSerializerOptions"/> for serializing and deserializing continuation tokens. Use this when the agent's continuation token contains custom types not registered in the default options. Falls back to <see cref="A2AHostingJsonUtilities.DefaultOptions"/> if not provided.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        AgentCard agentCard,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentSessionStore? agentSessionStore = null,
        AgentRunMode? runMode = null,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        taskManager = agent.MapA2A(taskManager, loggerFactory, agentSessionStore, runMode, jsonSerializerOptions);

        taskManager.OnAgentCardQuery += (context, query) =>
        {
            // A2A SDK assigns the url on its own
            // we can help user if they did not set Url explicitly.
            if (string.IsNullOrEmpty(agentCard.Url))
            {
                agentCard.Url = context.TrimEnd('/');
            }

            return Task.FromResult(agentCard);
        };
        return taskManager;
    }

    private static async Task<A2AResponse> OnMessageReceivedAsync(
        MessageSendParams messageSendParams,
        AIHostAgent hostAgent,
        AgentRunMode runMode,
        ITaskManager taskManager,
        JsonSerializerOptions continuationTokenJsonOptions,
        CancellationToken cancellationToken)
    {
        // AIAgent does not support resuming from arbitrary prior tasks.
        // Throw explicitly so the client gets a clear error rather than a response
        // that silently ignores the referenced task context.
        // Follow-ups on the *same* task are handled via OnTaskUpdated instead.
        if (messageSendParams.Message.ReferenceTaskIds is { Count: > 0 })
        {
            throw new NotSupportedException("ReferenceTaskIds is not supported. AIAgent cannot resume from arbitrary prior task context. Use OnTaskUpdated for follow-ups on the same task.");
        }

        var contextId = messageSendParams.Message.ContextId ?? Guid.NewGuid().ToString("N");
        var session = await hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

        // Decide whether to run in background based on user preferences and agent capabilities
        var decisionContext = new A2ARunDecisionContext(messageSendParams);
        var allowBackgroundResponses = await runMode.ShouldRunInBackgroundAsync(decisionContext, cancellationToken).ConfigureAwait(false);

        var options = messageSendParams.Metadata is not { Count: > 0 }
            ? new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses }
            : new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses, AdditionalProperties = messageSendParams.Metadata.ToAdditionalProperties() };

        var response = await hostAgent.RunAsync(
            messageSendParams.ToChatMessages(),
            session: session,
            options: options,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

        if (response.ContinuationToken is null)
        {
            return CreateMessageFromResponse(contextId, response);
        }

        var agentTask = await InitializeTaskAsync(contextId, messageSendParams.Message, taskManager, cancellationToken).ConfigureAwait(false);
        StoreContinuationToken(agentTask, response.ContinuationToken, continuationTokenJsonOptions);
        await TransitionToWorkingAsync(agentTask.Id, contextId, response, taskManager, cancellationToken).ConfigureAwait(false);
        return agentTask;
    }

    private static async Task OnTaskUpdatedAsync(
        AgentTask agentTask,
        AIHostAgent hostAgent,
        ITaskManager taskManager,
        JsonSerializerOptions continuationTokenJsonOptions,
        CancellationToken cancellationToken)
    {
        var contextId = agentTask.ContextId ?? Guid.NewGuid().ToString("N");
        var session = await hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

        try
        {
            // Discard any stale continuation token — the incoming user message supersedes
            // any previous background operation. AF agents don't support updating existing 
            // background responses (long-running operations); we start a fresh run from the
            // existing session using the full chat history (which includes the new message).
            agentTask.Metadata?.Remove(ContinuationTokenMetadataKey);

            await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, cancellationToken: cancellationToken).ConfigureAwait(false);

            var response = await hostAgent.RunAsync(
                ExtractChatMessagesFromTaskHistory(agentTask),
                session: session,
                options: new AgentRunOptions { AllowBackgroundResponses = true },
                cancellationToken: cancellationToken).ConfigureAwait(false);

            await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

            if (response.ContinuationToken is not null)
            {
                StoreContinuationToken(agentTask, response.ContinuationToken, continuationTokenJsonOptions);
                await TransitionToWorkingAsync(agentTask.Id, contextId, response, taskManager, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await CompleteWithArtifactAsync(agentTask.Id, response, taskManager, cancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception)
        {
            await taskManager.UpdateStatusAsync(
                agentTask.Id,
                TaskState.Failed,
                final: true,
                cancellationToken: cancellationToken).ConfigureAwait(false);
            throw;
        }
    }

    private static Task OnTaskCancelledAsync(AgentTask agentTask, CancellationToken cancellationToken)
    {
        // Remove the continuation token from metadata if present.
        // The task has already been marked as cancelled by the TaskManager.
        agentTask.Metadata?.Remove(ContinuationTokenMetadataKey);
        return Task.CompletedTask;
    }

    private static AgentMessage CreateMessageFromResponse(string contextId, AgentResponse response) =>
        new()
        {
            MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
            ContextId = contextId,
            Role = MessageRole.Agent,
            Parts = response.Messages.ToParts(),
            Metadata = response.AdditionalProperties?.ToA2AMetadata()
        };

    // Task outputs should be returned as artifacts rather than messages:
    // https://a2a-protocol.org/latest/specification/#37-messages-and-artifacts
    private static Artifact CreateArtifactFromResponse(AgentResponse response) =>
        new()
        {
            ArtifactId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
            Parts = response.Messages.ToParts(),
            Metadata = response.AdditionalProperties?.ToA2AMetadata()
        };

    private static async Task<AgentTask> InitializeTaskAsync(
        string contextId,
        AgentMessage originalMessage,
        ITaskManager taskManager,
        CancellationToken cancellationToken)
    {
        AgentTask agentTask = await taskManager.CreateTaskAsync(contextId, cancellationToken: cancellationToken).ConfigureAwait(false);

        // Add the original user message to the task history.
        // The A2A SDK does this internally when it creates tasks via OnTaskCreated.
        agentTask.History ??= [];
        agentTask.History.Add(originalMessage);

        // Notify subscribers of the Submitted state per the A2A spec: https://a2a-protocol.org/latest/specification/#413-taskstate
        await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Submitted, cancellationToken: cancellationToken).ConfigureAwait(false);

        return agentTask;
    }

    private static void StoreContinuationToken(
        AgentTask agentTask,
        ResponseContinuationToken token,
        JsonSerializerOptions continuationTokenJsonOptions)
    {
        // Serialize the continuation token into the task's metadata so it survives
        // across requests and is cleaned up with the task itself.
        agentTask.Metadata ??= [];
        agentTask.Metadata[ContinuationTokenMetadataKey] = JsonSerializer.SerializeToElement(
            token,
            continuationTokenJsonOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
    }

    private static async Task TransitionToWorkingAsync(
        string taskId,
        string contextId,
        AgentResponse response,
        ITaskManager taskManager,
        CancellationToken cancellationToken)
    {
        // Include any intermediate progress messages from the response as a status message.
        AgentMessage? progressMessage = response.Messages.Count > 0 ? CreateMessageFromResponse(contextId, response) : null;
        await taskManager.UpdateStatusAsync(taskId, TaskState.Working, message: progressMessage, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private static async Task CompleteWithArtifactAsync(
        string taskId,
        AgentResponse response,
        ITaskManager taskManager,
        CancellationToken cancellationToken)
    {
        var artifact = CreateArtifactFromResponse(response);
        await taskManager.ReturnArtifactAsync(taskId, artifact, cancellationToken).ConfigureAwait(false);
        await taskManager.UpdateStatusAsync(taskId, TaskState.Completed, final: true, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private static List<ChatMessage> ExtractChatMessagesFromTaskHistory(AgentTask agentTask)
    {
        if (agentTask.History is not { Count: > 0 })
        {
            return [];
        }

        var chatMessages = new List<ChatMessage>(agentTask.History.Count);
        foreach (var message in agentTask.History)
        {
            chatMessages.Add(message.ToChatMessage());
        }

        return chatMessages;
    }
}

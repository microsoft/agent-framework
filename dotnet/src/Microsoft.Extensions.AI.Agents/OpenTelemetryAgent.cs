// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents a delegating agent that implements OpenTelemetry instrumentation for agent operations.
/// </summary>
/// <remarks>
/// This class provides telemetry instrumentation for agent operations including activities, metrics, and logging.
/// The telemetry output follows OpenTelemetry semantic conventions in <see href="https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/"/> and is subject to change as the conventions evolve.
/// </remarks>
public sealed class OpenTelemetryAgent : Agent, IDisposable
{
    private readonly Agent _innerAgent;
    private readonly ActivitySource _activitySource;
    private readonly Meter _meter;
    private readonly Histogram<double> _operationDurationHistogram;
    private readonly Histogram<int> _tokenUsageHistogram;
    private readonly Counter<int> _requestCounter;

    /// <summary>
    /// Initializes a new instance of the <see cref="OpenTelemetryAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent to wrap with telemetry.</param>
    /// <param name="sourceName">An optional source name that will be used on the telemetry data.</param>
    public OpenTelemetryAgent(Agent innerAgent, string? sourceName = null)
    {
        this._innerAgent = Throw.IfNull(innerAgent);

        string name = string.IsNullOrEmpty(sourceName) ? AgentOpenTelemetryConsts.DefaultSourceName : sourceName!;
        this._activitySource = new(name);
        this._meter = new(name);

        this._operationDurationHistogram = this._meter.CreateHistogram<double>(
            AgentOpenTelemetryConsts.GenAI.Agent.Client.OperationDuration.Name,
            AgentOpenTelemetryConsts.SecondsUnit,
            AgentOpenTelemetryConsts.GenAI.Agent.Client.OperationDuration.Description
#if NET9_0_OR_GREATER
            , advice: new() { HistogramBucketBoundaries = AgentOpenTelemetryConsts.GenAI.Agent.Client.OperationDuration.ExplicitBucketBoundaries }
#endif
            );

        this._tokenUsageHistogram = this._meter.CreateHistogram<int>(
            AgentOpenTelemetryConsts.GenAI.Agent.Client.TokenUsage.Name,
            AgentOpenTelemetryConsts.TokensUnit,
            AgentOpenTelemetryConsts.GenAI.Agent.Client.TokenUsage.Description
#if NET9_0_OR_GREATER
            , advice: new() { HistogramBucketBoundaries = AgentOpenTelemetryConsts.GenAI.Agent.Client.TokenUsage.ExplicitBucketBoundaries }
#endif
            );

        this._requestCounter = this._meter.CreateCounter<int>(
            AgentOpenTelemetryConsts.GenAI.Agent.Client.RequestCount.Name,
            description: AgentOpenTelemetryConsts.GenAI.Agent.Client.RequestCount.Description);
    }

    /// <inheritdoc/>
    public override string Id => this._innerAgent.Id;

    /// <inheritdoc/>
    public override string? Name => this._innerAgent.Name;

    /// <inheritdoc/>
    public override string? Description => this._innerAgent.Description;

    /// <inheritdoc/>
    public override AgentThread GetNewThread() => this._innerAgent.GetNewThread();

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        using Activity? activity = this.CreateAndConfigureActivity(AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent, messages, thread);
        Stopwatch? stopwatch = this._operationDurationHistogram.Enabled ? Stopwatch.StartNew() : null;

        AgentRunResponse? response = null;
        Exception? error = null;

        try
        {
            response = await this._innerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);
            return response;
        }
        catch (Exception ex)
        {
            error = ex;
            throw;
        }
        finally
        {
            this.TraceResponse(activity, response, error, stopwatch, messages.Count, isStreaming: false);
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        using Activity? activity = this.CreateAndConfigureActivity(AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent, messages, thread);
        Stopwatch? stopwatch = this._operationDurationHistogram.Enabled ? Stopwatch.StartNew() : null;

        IAsyncEnumerable<AgentRunResponseUpdate> updates;
        try
        {
            updates = this._innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
        }
        catch (Exception ex)
        {
            this.TraceResponse(activity, response: null, ex, stopwatch, messages.Count, isStreaming: true);
            throw;
        }

        var responseEnumerator = updates.GetAsyncEnumerator(cancellationToken);
        List<AgentRunResponseUpdate> trackedUpdates = [];
        Exception? error = null;

        try
        {
            while (true)
            {
                AgentRunResponseUpdate update;
                try
                {
                    if (!await responseEnumerator.MoveNextAsync().ConfigureAwait(false))
                    {
                        break;
                    }
                    update = responseEnumerator.Current;
                }
                catch (Exception ex)
                {
                    error = ex;
                    throw;
                }

                trackedUpdates.Add(update);
                yield return update;
                Activity.Current = activity; // workaround for https://github.com/dotnet/runtime/issues/47802
            }
        }
        finally
        {
            this.TraceResponse(activity, trackedUpdates.ToAgentRunResponse(), error, stopwatch, messages.Count, isStreaming: true);
            await responseEnumerator.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Disposes the telemetry resources.
    /// </summary>
    public void Dispose()
    {
        this._activitySource.Dispose();
        this._meter.Dispose();
    }

    /// <summary>
    /// Creates an activity for an agent request, or returns null if not enabled.
    /// </summary>
    private Activity? CreateAndConfigureActivity(string operationName, IReadOnlyCollection<ChatMessage> messages, AgentThread? thread)
    {
        // Get the GenAI system name for telemetry
        var chatClientAgent = this._innerAgent as ChatClientAgent;
        var genAISystem = chatClientAgent?.ChatClient.GetService<ChatClientMetadata>()?.ProviderName;
        Activity? activity = null;
        if (this._activitySource.HasListeners())
        {
            string activityName = string.IsNullOrWhiteSpace(this.Name) ? operationName : $"{operationName} {this.Name}";
            activity = this._activitySource.StartActivity(activityName, ActivityKind.Client);

            if (activity is not null)
            {
                _ = activity
                    // Required attributes per OpenTelemetry semantic conventions
                    .AddTag(AgentOpenTelemetryConsts.GenAI.OperationName, operationName)
                    .AddTag(AgentOpenTelemetryConsts.GenAI.System, genAISystem ?? AgentOpenTelemetryConsts.GenAI.Systems.MicrosoftExtensionsAI)
                    // Agent-specific attributes
                    .AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Id, this.Id)
                    .AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Request.MessageCount, messages.Count);

                // Add agent name if available (following gen_ai.agent.name convention - conditionally required when available)
                if (!string.IsNullOrWhiteSpace(this.Name))
                {
                    _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Name, this.Name);
                }

                // Add description if available (following gen_ai.agent.description convention)
                if (!string.IsNullOrWhiteSpace(this.Description))
                {
                    _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Description, this.Description);
                }

                // Add conversation ID if thread is available (following gen_ai.conversation.id convention)
                if (!string.IsNullOrWhiteSpace(thread?.Id))
                {
                    _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.ConversationId, thread.Id);
                }

                // Add instructions if available (for ChatClientAgent)
                if (!string.IsNullOrWhiteSpace(chatClientAgent?.Instructions))
                {
                    _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Request.Instructions, chatClientAgent.Instructions);
                }
            }
        }

        return activity;
    }

    /// <summary>
    /// Adds a tag to the tag list if the value is not null or whitespace.
    /// </summary>
    private static void AddIfNotWhiteSpace(ref TagList tags, string key, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            tags.Add(key, value);
        }
    }

    /// <summary>
    /// Adds agent response information to the activity and records metrics.
    /// </summary>
    private void TraceResponse(
        Activity? activity,
        AgentRunResponse? response,
        Exception? error,
        Stopwatch? stopwatch,
        int inputMessageCount,
        bool isStreaming)
    {
        // Record operation duration metric
        if (this._operationDurationHistogram.Enabled && stopwatch is not null)
        {
            TagList tags = new()
            {
                { AgentOpenTelemetryConsts.GenAI.OperationName, AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent }
            };

            AddIfNotWhiteSpace(ref tags, AgentOpenTelemetryConsts.GenAI.Agent.Name, this.Name);

            if (error is not null)
            {
                tags.Add(AgentOpenTelemetryConsts.ErrorInfo.Type, error.GetType().FullName);
            }

            this._operationDurationHistogram.Record(stopwatch.Elapsed.TotalSeconds, tags);
        }

        // Record request count metric
        if (this._requestCounter.Enabled)
        {
            TagList tags = new()
            {
                { AgentOpenTelemetryConsts.GenAI.OperationName, AgentOpenTelemetryConsts.GenAI.Operations.InvokeAgent }
            };

            AddIfNotWhiteSpace(ref tags, AgentOpenTelemetryConsts.GenAI.Agent.Name, this.Name);

            this._requestCounter.Add(1, tags);
        }

        // Record token usage metrics
        if (this._tokenUsageHistogram.Enabled && response?.Usage is { } usage)
        {
            if (usage.InputTokenCount is long inputTokens)
            {
                TagList tags = new()
                {
                    { AgentOpenTelemetryConsts.GenAI.Agent.Token.Type, "input" }
                };

                AddIfNotWhiteSpace(ref tags, AgentOpenTelemetryConsts.GenAI.Agent.Name, this.Name);

                this._tokenUsageHistogram.Record((int)inputTokens, tags);
            }

            if (usage.OutputTokenCount is long outputTokens)
            {
                TagList tags = new()
                {
                    { AgentOpenTelemetryConsts.GenAI.Agent.Token.Type, "output" }
                };

                AddIfNotWhiteSpace(ref tags, AgentOpenTelemetryConsts.GenAI.Agent.Name, this.Name);

                this._tokenUsageHistogram.Record((int)outputTokens, tags);
            }
        }

        // Add activity tags
        if (activity is not null)
        {
            if (error is not null)
            {
                _ = activity
                    .AddTag(AgentOpenTelemetryConsts.ErrorInfo.Type, error.GetType().FullName)
                    .SetStatus(ActivityStatusCode.Error, error.Message);
            }

            if (response is not null)
            {
                _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Response.MessageCount, response.Messages.Count);

                if (!string.IsNullOrWhiteSpace(response.ResponseId))
                {
                    _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Response.Id, response.ResponseId);
                }

                if (response.Usage?.InputTokenCount is long inputTokens)
                {
                    _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Usage.InputTokens, (int)inputTokens);
                }

                if (response.Usage?.OutputTokenCount is long outputTokens)
                {
                    _ = activity.AddTag(AgentOpenTelemetryConsts.GenAI.Agent.Usage.OutputTokens, (int)outputTokens);
                }
            }
        }
    }
}

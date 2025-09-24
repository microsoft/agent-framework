// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents a delegating agent that implements OpenTelemetry instrumentation for agent operations.
/// </summary>
/// <remarks>
/// This class provides telemetry instrumentation for agent operations including activities, metrics, and logging.
/// The telemetry output follows OpenTelemetry semantic conventions in <see href="https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/"/> and is subject to change as the conventions evolve.
/// </remarks>
public sealed partial class OpenTelemetryAgent : DelegatingAIAgent, IDisposable
{
    private const LogLevel EventLogLevel = LogLevel.Information;
    private JsonSerializerOptions _jsonSerializerOptions;
    private readonly OpenTelemetryChatClient? _openTelemetryChatClient;
    private readonly string? _system;
    private readonly ActivitySource _activitySource;
    private readonly Meter _meter;
    private readonly Histogram<double> _operationDurationHistogram;
    private readonly Histogram<int> _tokenUsageHistogram;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="OpenTelemetryAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent to wrap with telemetry.</param>
    /// <param name="logger">The <see cref="ILogger"/> to use for emitting events.</param>
    /// <param name="sourceName">An optional source name that will be used on the telemetry data.</param>
    public OpenTelemetryAgent(AIAgent innerAgent, ILogger? logger = null, string? sourceName = null)
        : base(innerAgent)
    {
        string name = string.IsNullOrEmpty(sourceName) ? OpenTelemetryConsts.DefaultSourceName : sourceName!;
        this._activitySource = new(name);
        this._meter = new(name);
        this._logger = logger ?? NullLogger.Instance;
        this._system = this.GetService<AIAgentMetadata>()?.ProviderName ?? OpenTelemetryConsts.GenAI.SystemNameValues.MicrosoftExtensionsAIAgents;

        // Attempt to get the open telemetry chat client if the inner agent is a ChatClientAgent.
        this._openTelemetryChatClient = (this.InnerAgent as ChatClientAgent)?.ChatClient.GetService<OpenTelemetryChatClient>();

        // Inherit by default the EnableSensitiveData setting from the TelemetryChatClient if available.
        this.EnableSensitiveData = this._openTelemetryChatClient?.EnableSensitiveData ?? false;

        this._operationDurationHistogram = this._meter.CreateHistogram<double>(
            OpenTelemetryConsts.GenAI.Client.OperationDuration.Name,
            OpenTelemetryConsts.SecondsUnit,
            OpenTelemetryConsts.GenAI.Client.OperationDuration.Description
#if NET9_0_OR_GREATER
            , advice: new() { HistogramBucketBoundaries = OpenTelemetryConsts.GenAI.Client.OperationDuration.ExplicitBucketBoundaries }
#endif
            );

        this._tokenUsageHistogram = this._meter.CreateHistogram<int>(
            OpenTelemetryConsts.GenAI.Client.TokenUsage.Name,
            OpenTelemetryConsts.TokensUnit,
            OpenTelemetryConsts.GenAI.Client.TokenUsage.Description
#if NET9_0_OR_GREATER
            , advice: new() { HistogramBucketBoundaries = OpenTelemetryConsts.GenAI.Client.TokenUsage.ExplicitBucketBoundaries }
#endif
            );

        this._jsonSerializerOptions = AIJsonUtilities.DefaultOptions;
    }

    /// <summary>Gets or sets JSON serialization options to use when formatting chat data into telemetry strings.</summary>
    public JsonSerializerOptions JsonSerializerOptions
    {
        get => this._jsonSerializerOptions;
        set => this._jsonSerializerOptions = Throw.IfNull(value);
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
    /// Gets or sets a value indicating whether potentially sensitive information should be included in telemetry.
    /// </summary>
    /// <value>
    /// <see langword="true"/> if potentially sensitive information should be included in telemetry;
    /// <see langword="false"/> if telemetry shouldn't include raw inputs and outputs.
    /// The default value is <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// By default, telemetry includes metadata, such as token counts, but not raw inputs
    /// and outputs, such as message content, function call arguments, and function call results.
    /// </remarks>
    public bool EnableSensitiveData { get; set; }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        // Handle ActivitySource requests directly - always return our own ActivitySource
        if (serviceType == typeof(ActivitySource))
        {
            return this._activitySource;
        }

        // For other service types, use the base delegation logic
        return base.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        using Activity? activity = this.CreateAndConfigureActivity(OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent, thread);
        Stopwatch? stopwatch = this._operationDurationHistogram.Enabled ? Stopwatch.StartNew() : null;

        this.LogChatMessages(inputMessages);

        AgentRunResponse? response = null;
        Exception? error = null;
        try
        {
            response = await base.RunAsync(inputMessages, thread, options, cancellationToken).ConfigureAwait(false);
            return response;
        }
        catch (Exception ex)
        {
            error = ex;
            throw;
        }
        finally
        {
            this.TraceResponse(activity, response, error, stopwatch);
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        using Activity? activity = this.CreateAndConfigureActivity(OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent, thread);
        Stopwatch? stopwatch = this._operationDurationHistogram.Enabled ? Stopwatch.StartNew() : null;

        IAsyncEnumerable<AgentRunResponseUpdate> updates;
        try
        {
            updates = base.RunStreamingAsync(inputMessages, thread, options, cancellationToken);
        }
        catch (Exception ex)
        {
            this.TraceResponse(activity, response: null, ex, stopwatch);
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
            this.TraceResponse(activity, trackedUpdates.ToAgentRunResponse(), error, stopwatch);
            await responseEnumerator.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Creates an activity for an agent request, or returns null if not enabled.
    /// </summary>
    private Activity? CreateAndConfigureActivity(string operationName, AgentThread? thread)
    {
        // Get the GenAI system name for telemetry
        var chatClientAgent = this.InnerAgent as ChatClientAgent;
        Activity? activity = null;
        if (this._activitySource.HasListeners())
        {
            string activityName = string.IsNullOrWhiteSpace(this.Name) ? operationName : $"{operationName} {this.Name}";
            activity = this._activitySource.StartActivity(activityName, ActivityKind.Client);

            if (activity is not null)
            {
                _ = activity
                    // Required attributes per OpenTelemetry semantic conventions
                    .AddTag(OpenTelemetryConsts.GenAI.Operation.Name, operationName)
                    .AddTag(OpenTelemetryConsts.GenAI.SystemName, this._system)
                    // Agent-specific attributes
                    .AddTag(OpenTelemetryConsts.GenAI.Agent.Id, this.Id);

                // Add agent name if available (following gen_ai.agent.name convention - conditionally required when available)
                if (!string.IsNullOrWhiteSpace(this.Name))
                {
                    _ = activity.AddTag(OpenTelemetryConsts.GenAI.Agent.Name, this.Name);
                }

                // Add description if available (following gen_ai.agent.description convention)
                if (!string.IsNullOrWhiteSpace(this.Description))
                {
                    _ = activity.AddTag(OpenTelemetryConsts.GenAI.Agent.Description, this.Description);
                }

                // Add conversation ID if thread is available (following gen_ai.conversation.id convention)
                var metadata = thread?.GetService<AgentThreadMetadata>();
                if (!string.IsNullOrWhiteSpace(metadata?.ConversationId))
                {
                    _ = activity.AddTag(OpenTelemetryConsts.GenAI.Conversation.Id, metadata.ConversationId);
                }

                // Add instructions if available (for ChatClientAgent)
                if (!string.IsNullOrWhiteSpace(chatClientAgent?.Instructions))
                {
                    _ = activity.AddTag(OpenTelemetryConsts.GenAI.Request.Instructions, chatClientAgent.Instructions);
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
        Stopwatch? stopwatch)
    {
        // Record operation duration metric
        if (this._operationDurationHistogram.Enabled && stopwatch is not null)
        {
            TagList tags = new()
            {
                { OpenTelemetryConsts.GenAI.Operation.Name, OpenTelemetryConsts.GenAI.Operation.NameValues.InvokeAgent }
            };

            AddIfNotWhiteSpace(ref tags, OpenTelemetryConsts.GenAI.Agent.Name, this.DisplayName);

            if (error is not null)
            {
                tags.Add(OpenTelemetryConsts.Error.Type, error.GetType().FullName);
            }

            this._operationDurationHistogram.Record(stopwatch.Elapsed.TotalSeconds, tags);
        }

        // Record token usage metrics
        if (this._tokenUsageHistogram.Enabled && response?.Usage is { } usage)
        {
            if (usage.InputTokenCount is long inputTokens)
            {
                TagList tags = new()
                {
                    { OpenTelemetryConsts.GenAI.Token.Type, "input" }
                };

                AddIfNotWhiteSpace(ref tags, OpenTelemetryConsts.GenAI.Agent.Name, this.Name);

                this._tokenUsageHistogram.Record((int)inputTokens, tags);
            }

            if (usage.OutputTokenCount is long outputTokens)
            {
                TagList tags = new()
                {
                    { OpenTelemetryConsts.GenAI.Token.Type, "output" }
                };

                AddIfNotWhiteSpace(ref tags, OpenTelemetryConsts.GenAI.Agent.Name, this.Name);

                this._tokenUsageHistogram.Record((int)outputTokens, tags);
            }
        }

        // Add activity tags
        if (activity is not null)
        {
            if (error is not null)
            {
                _ = activity
                    .AddTag(OpenTelemetryConsts.Error.Type, error.GetType().FullName)
                    .SetStatus(ActivityStatusCode.Error, error.Message);
            }

            if (response is not null)
            {
                if (!string.IsNullOrWhiteSpace(response.ResponseId))
                {
                    _ = activity.AddTag(OpenTelemetryConsts.GenAI.Response.Id, response.ResponseId);
                }

                if (response.Usage?.InputTokenCount is long inputTokens)
                {
                    _ = activity.AddTag(OpenTelemetryConsts.GenAI.Usage.InputTokens, (int)inputTokens);
                }

                if (response.Usage?.OutputTokenCount is long outputTokens)
                {
                    _ = activity.AddTag(OpenTelemetryConsts.GenAI.Usage.OutputTokens, (int)outputTokens);
                }
            }
        }

        // Log the agent response for choice events
        if (response is not null)
        {
            this.LogAgentResponse(response);
        }
    }

    private void LogChatMessages(IEnumerable<ChatMessage> messages)
    {
        if (this._openTelemetryChatClient is not null)
        {
            // To avoid duplication of telemetry data the logging will be skipped if the agent is a ChatClientAgent and
            // its innerChatClient already has telemetry enabled, 
            return;
        }

        if (!this._logger.IsEnabled(EventLogLevel))
        {
            return;
        }

        foreach (ChatMessage message in messages)
        {
            if (message.Role == ChatRole.Assistant)
            {
                this.Log(new EventId(1, OpenTelemetryConsts.GenAI.Assistant.Message),
                    JsonSerializer.Serialize(this.CreateAssistantEvent(message.Contents), OtelContext.Default.AssistantEvent));
            }
            else if (message.Role == ChatRole.Tool)
            {
                foreach (FunctionResultContent frc in message.Contents.OfType<FunctionResultContent>())
                {
                    this.Log(new EventId(1, OpenTelemetryConsts.GenAI.Tool.Message),
                        JsonSerializer.Serialize(new ToolEvent()
                        {
                            Id = frc.CallId,
                            Content = this.EnableSensitiveData && frc.Result is object result ?
                                JsonSerializer.SerializeToNode(result, this._jsonSerializerOptions.GetTypeInfo(result.GetType())) :
                                null,
                        }, OtelContext.Default.ToolEvent));
                }
            }
            else
            {
                this.Log(new EventId(1, message.Role == ChatRole.System ? OpenTelemetryConsts.GenAI.System.Message : OpenTelemetryConsts.GenAI.User.Message),
                    JsonSerializer.Serialize(new SystemOrUserEvent()
                    {
                        Role = message.Role != ChatRole.System && message.Role != ChatRole.User && !string.IsNullOrWhiteSpace(message.Role.Value) ? message.Role.Value : null,
                        Content = this.GetMessageContent(message.Contents),
                    }, OtelContext.Default.SystemOrUserEvent));
            }
        }
    }

    private void LogAgentResponse(AgentRunResponse response)
    {
        if (this._openTelemetryChatClient is not null)
        {
            // To avoid duplication of telemetry data the logging will be skipped if the agent is a ChatClientAgent and
            // its innerChatClient already has telemetry enabled
            return;
        }

        if (!this._logger.IsEnabled(EventLogLevel))
        {
            return;
        }

        EventId id = new(1, OpenTelemetryConsts.GenAI.Choice);
        this.Log(id, JsonSerializer.Serialize(new ChoiceEvent()
        {
            FinishReason = (response.RawRepresentation as ChatResponse)?.FinishReason?.Value ?? string.Empty,
            Index = 0,
            Message = this.CreateAssistantEvent(response.Messages is { Count: 1 } ? response.Messages[0].Contents : response.Messages.SelectMany(m => m.Contents)),
        }, OtelContext.Default.ChoiceEvent));
    }

    private void Log(EventId id, string eventBodyJson)
    {
        // This is not the idiomatic way to log, but it's necessary for now in order to structure
        // the data in a way that the OpenTelemetry collector can work with it. The event body
        // can be very large and should not be logged as an attribute.

        KeyValuePair<string, object?>[] tags =
        [
            new(OpenTelemetryConsts.Event.Name, id.Name),
            new(OpenTelemetryConsts.GenAI.SystemName, this._system),
        ];

        this._logger.Log(EventLogLevel, id, tags, null, (_, __) => eventBodyJson);
    }

    private AssistantEvent CreateAssistantEvent(IEnumerable<AIContent> contents)
    {
        var toolCalls = contents.OfType<FunctionCallContent>().Select(fc => new ToolCall
        {
            Id = fc.CallId,
            Function = new()
            {
                Name = fc.Name,
                Arguments = this.EnableSensitiveData ?
                    JsonSerializer.SerializeToNode(fc.Arguments, this._jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>))) :
                    null,
            },
        }).ToArray();

        return new()
        {
            Content = this.GetMessageContent(contents),
            ToolCalls = toolCalls.Length > 0 ? toolCalls : null,
        };
    }

    private string? GetMessageContent(IEnumerable<AIContent> contents)
    {
        if (this.EnableSensitiveData)
        {
            string content = string.Concat(contents.OfType<TextContent>());
            if (content.Length > 0)
            {
                return content;
            }
        }

        return null;
    }

    private sealed partial class SystemOrUserEvent
    {
        public string? Role { get; set; }
        public string? Content { get; set; }
    }

    private sealed class AssistantEvent
    {
        public string? Content { get; set; }
        public ToolCall[]? ToolCalls { get; set; }
    }

    private sealed partial class ToolEvent
    {
        public string? Id { get; set; }
        public JsonNode? Content { get; set; }
    }

    private sealed partial class ChoiceEvent
    {
        public string? FinishReason { get; set; }
        public int Index { get; set; }
        public AssistantEvent? Message { get; set; }
    }

    private sealed partial class ToolCall
    {
        public string? Id { get; set; }
        public string? Type { get; set; } = "function";
        public ToolCallFunction? Function { get; set; }
    }

    private sealed partial class ToolCallFunction
    {
        public string? Name { get; set; }
        public JsonNode? Arguments { get; set; }
    }

    [JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonSerializable(typeof(SystemOrUserEvent))]
    [JsonSerializable(typeof(AssistantEvent))]
    [JsonSerializable(typeof(ToolEvent))]
    [JsonSerializable(typeof(ChoiceEvent))]
    [JsonSerializable(typeof(object))]
    private sealed partial class OtelContext : JsonSerializerContext;
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a delegating <see cref="AIAgent"/> implementation that implements the OpenTelemetry Semantic Conventions for Generative AI systems.
/// </summary>
/// <remarks>
/// This class provides an implementation of the Semantic Conventions for Generative AI systems v1.37, defined at <see href="https://opentelemetry.io/docs/specs/semconv/gen-ai/" />.
/// The specification is still experimental and subject to change; as such, the telemetry output by this client is also subject to change.
/// </remarks>
public sealed class OpenTelemetryAgent : DelegatingAIAgent, IDisposable
{
    // IMPLEMENTATION NOTE: The OpenTelemetryChatClient from Microsoft.Extensions.AI provides a full and up-to-date
    // implementationof the OpenTelemetry Semantic Conventions for Generative AI systems, specifically for the client
    // metrics and the chat span. But the chat span is almost identical to the invoke_agent span, just with invoke_agent
    // have a different value for the operation name and a few additional tags. To avoid needing to reimplement the
    // convention, then, and keep it up-to-date as the convention evolves, for now this implementation just delegates
    // to OpenTelemetryChatClient for the actual telemetry work. For RunAsync and RunStreamingAsync, it delegates to the
    // inner agent not directly but rather via OpenTelemetryChatClient, which wraps a ForwardingChatClient that in turn
    // calls back into the inner agent.

    /// <summary>The <see cref="OpenTelemetryChatClient"/> providing the bulk of the telemetry.</summary>
    private readonly OpenTelemetryChatClient _otelClient;
    /// <summary>The provider name extracted from <see cref="AIAgentMetadata"/>.</summary>
    private readonly string? _providerName;
    /// <summary>The resolved source name for telemetry. Always non-empty; defaults to <see cref="OpenTelemetryConsts.DefaultSourceName"/>.</summary>
    private readonly string _sourceName;
    /// <summary>
    /// Indicates whether the underlying <see cref="IChatClient"/> of a <see cref="ChatClientAgent"/> inner agent
    /// should be automatically wrapped with <see cref="OpenTelemetryChatClient"/> on each invocation.
    /// </summary>
    private readonly bool _autoWireChatClient;

    /// <summary>Initializes a new instance of the <see cref="OpenTelemetryAgent"/> class.</summary>
    /// <param name="innerAgent">The underlying <see cref="AIAgent"/> to be augmented with telemetry capabilities.</param>
    /// <param name="sourceName">
    /// An optional source name that will be used to identify telemetry data from this agent.
    /// If not provided, a default source name will be used for telemetry identification.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The constructor automatically extracts provider metadata from the inner agent and configures
    /// telemetry collection according to OpenTelemetry semantic conventions for AI systems.
    /// </remarks>
    public OpenTelemetryAgent(AIAgent innerAgent, string? sourceName = null)
#pragma warning disable MAAI001 // Auto-wiring is the new default; the experimental opt-out lives on the 3-arg overload.
        : this(innerAgent, sourceName, autoWireChatClient: true)
#pragma warning restore MAAI001
    {
    }

    /// <summary>Initializes a new instance of the <see cref="OpenTelemetryAgent"/> class.</summary>
    /// <param name="innerAgent">The underlying <see cref="AIAgent"/> to be augmented with telemetry capabilities.</param>
    /// <param name="sourceName">
    /// An optional source name that will be used to identify telemetry data from this agent.
    /// If not provided, a default source name will be used for telemetry identification.
    /// </param>
    /// <param name="autoWireChatClient">
    /// When <see langword="true"/> and the inner agent is a <see cref="ChatClientAgent"/>, the underlying
    /// <see cref="IChatClient"/> is automatically wrapped with <see cref="OpenTelemetryChatClient"/> for each invocation
    /// so that chat-level telemetry flows alongside agent-level telemetry. If the underlying chat client is already
    /// instrumented, no additional wrapping is applied. Set to <see langword="false"/> to opt-out of this behavior.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The constructor automatically extracts provider metadata from the inner agent and configures
    /// telemetry collection according to OpenTelemetry semantic conventions for AI systems.
    /// </remarks>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public OpenTelemetryAgent(AIAgent innerAgent, string? sourceName, bool autoWireChatClient) : base(innerAgent)
    {
        this._providerName = innerAgent.GetService<AIAgentMetadata>()?.ProviderName;

        // Resolve once so the outer OpenTelemetryChatClient and the auto-wired inner
        // OpenTelemetryChatClient always emit spans under the same ActivitySource, even when
        // the caller passes "" or whitespace (which neither client should treat as a real source).
        this._sourceName = string.IsNullOrWhiteSpace(sourceName) ? OpenTelemetryConsts.DefaultSourceName : sourceName!;
        this._autoWireChatClient = autoWireChatClient;

        this._otelClient = new OpenTelemetryChatClient(
            new ForwardingChatClient(this),
            sourceName: this._sourceName);
    }

    /// <inheritdoc/>
    public void Dispose() => this._otelClient.Dispose();

    /// <summary>
    /// Gets or sets a value indicating whether potentially sensitive information should be included in telemetry.
    /// </summary>
    /// <value>
    /// <see langword="true"/> if potentially sensitive information should be included in telemetry;
    /// <see langword="false"/> if telemetry shouldn't include raw inputs and outputs.
    /// The default value is <see langword="false"/>, unless the <c>OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT</c>
    /// environment variable is set to "true" (case-insensitive).
    /// </value>
    /// <remarks>
    /// By default, telemetry includes metadata, such as token counts, but not raw inputs
    /// and outputs, such as message content, function call arguments, and function call results.
    /// The default value can be overridden by setting the <c>OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT</c>
    /// environment variable to "true". Explicitly setting this property will override the environment variable.
    /// <para>
    /// <strong>Security consideration:</strong> When sensitive data capture is enabled, the full text of chat messages —
    /// including user inputs, LLM responses, function call arguments, and function results — is emitted as telemetry.
    /// This data may contain PII or other sensitive information. Ensure that your telemetry pipeline is configured
    /// with appropriate access controls and data retention policies.
    /// </para>
    /// </remarks>
    public bool EnableSensitiveData
    {
        get => this._otelClient.EnableSensitiveData;
        set => this._otelClient.EnableSensitiveData = value;
    }

    /// <inheritdoc/>
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        ChatOptions co = new ForwardedOptions(options, session, Activity.Current);

        var response = await this._otelClient.GetResponseAsync(messages, co, cancellationToken).ConfigureAwait(false);

        return response.RawRepresentation as AgentResponse ?? new AgentResponse(response);
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ChatOptions co = new ForwardedOptions(options, session, Activity.Current);

        await foreach (var update in this._otelClient.GetStreamingResponseAsync(messages, co, cancellationToken).ConfigureAwait(false))
        {
            yield return update.RawRepresentation as AgentResponseUpdate ?? new AgentResponseUpdate(update);
        }
    }

    /// <summary>Augments the current activity created by the <see cref="OpenTelemetryChatClient"/> with agent-specific information.</summary>
    /// <param name="previousActivity">The <see cref="Activity"/> that was current prior to the <see cref="OpenTelemetryChatClient"/>'s invocation.</param>
    private void UpdateCurrentActivity(Activity? previousActivity)
    {
        // If there isn't a current activity to augment, or it's the same one that was current when the agent was invoked (meaning
        // the OpenTelemetryChatClient didn't create one), then there's nothing to do.
        if (Activity.Current is not { } activity ||
            ReferenceEquals(activity, previousActivity))
        {
            return;
        }

        // Override information set by OpenTelemetryChatClient to make it specific to invoke_agent.

        activity.DisplayName = string.IsNullOrWhiteSpace(this.Name)
            ? $"{OpenTelemetryConsts.GenAI.InvokeAgent} {this.Id}"
            : $"{OpenTelemetryConsts.GenAI.InvokeAgent} {this.Name}({this.Id})";
        activity.SetTag(OpenTelemetryConsts.GenAI.Operation.Name, OpenTelemetryConsts.GenAI.InvokeAgent);

        if (!string.IsNullOrWhiteSpace(this._providerName))
        {
            _ = activity.SetTag(OpenTelemetryConsts.GenAI.Provider.Name, this._providerName);
        }

        // Further augment the activity with agent-specific tags.

        _ = activity.SetTag(OpenTelemetryConsts.GenAI.Agent.Id, this.Id);

        if (this.Name is { } name && !string.IsNullOrWhiteSpace(name))
        {
            _ = activity.SetTag(OpenTelemetryConsts.GenAI.Agent.Name, this.Name);
        }

        if (this.Description is { } description && !string.IsNullOrWhiteSpace(description))
        {
            _ = activity.SetTag(OpenTelemetryConsts.GenAI.Agent.Description, description);
        }
    }

    /// <summary>State passed from this instance into the inner agent, circumventing the intermediate <see cref="OpenTelemetryChatClient"/>.</summary>
    private sealed class ForwardedOptions : ChatOptions
    {
        public ForwardedOptions(AgentRunOptions? options, AgentSession? session, Activity? currentActivity) :
            base((options as ChatClientAgentRunOptions)?.ChatOptions)
        {
            this.Options = options;
            this.Session = session;
            this.CurrentActivity = currentActivity;
        }

        public AgentRunOptions? Options { get; }

        public AgentSession? Session { get; }

        public Activity? CurrentActivity { get; }
    }

    /// <summary>
    /// If auto-wiring is enabled and the inner agent is a <see cref="ChatClientAgent"/> whose underlying
    /// <see cref="IChatClient"/> is not already instrumented with <see cref="OpenTelemetryChatClient"/>, returns a
    /// new <see cref="ChatClientAgentRunOptions"/> with a <see cref="ChatClientAgentRunOptions.ChatClientFactory"/>
    /// that wraps the chat client with <see cref="OpenTelemetryChatClient"/>. When <paramref name="options"/> is a
    /// plain <see cref="AgentRunOptions"/> (the base type, not <see cref="ChatClientAgentRunOptions"/>), the base
    /// properties are copied onto the new <see cref="ChatClientAgentRunOptions"/> so high-level callers that pass
    /// the abstract <see cref="AgentRunOptions"/> still benefit from auto-wiring and propagate their settings to
    /// the inner agent. Otherwise, returns <paramref name="options"/> unchanged.
    /// </summary>
    private AgentRunOptions? GetRunOptionsWithChatClientWiring(AgentRunOptions? options)
    {
        if (!this._autoWireChatClient)
        {
            return options;
        }

        // The auto-wiring only applies when a ChatClientAgent is reachable from the inner agent. Otherwise, no-op.
        // Use GetService rather than a type check so wrapping agents that expose a nested ChatClientAgent are supported.
        var chatClientAgent = this.InnerAgent.GetService<ChatClientAgent>();
        if (chatClientAgent is null)
        {
            return options;
        }

        // Respect ChatClientAgentOptions.UseProvidedChatClientAsIs: don't decorate the chat client when the user opted out.
        if (chatClientAgent.GetService<ChatClientAgentOptions>()?.UseProvidedChatClientAsIs is true)
        {
            return options;
        }

        // Capture the underlying IChatClient and check whether it is already instrumented.
        var chatClient = chatClientAgent.GetService<IChatClient>();
        if (chatClient is null || chatClient.GetService(typeof(OpenTelemetryChatClient)) is not null)
        {
            return options;
        }

        string sourceName = this._sourceName;
        static IChatClient WrapIfNeeded(IChatClient cc, string sourceName) =>
            cc.GetService(typeof(OpenTelemetryChatClient)) is not null
                ? cc
                : cc.AsBuilder().UseOpenTelemetry(sourceName: sourceName).Build();

        if (options is ChatClientAgentRunOptions ccOptions)
        {
            // Don't mutate the caller's options; clone and chain any caller-provided factory.
            // If the user factory already returns an OpenTelemetry-instrumented client, don't double-wrap.
            var clone = (ChatClientAgentRunOptions)ccOptions.Clone();
            var userFactory = clone.ChatClientFactory;
            clone.ChatClientFactory = cc => WrapIfNeeded(userFactory is null ? cc : userFactory(cc), sourceName);
            return clone;
        }

        // For a plain AgentRunOptions (or null), create a ChatClientAgentRunOptions and preserve
        // any base AgentRunOptions properties from the caller so they reach the inner agent.
        var newOptions = new ChatClientAgentRunOptions
        {
            ChatClientFactory = cc => WrapIfNeeded(cc, sourceName),
        };

        if (options is not null)
        {
            CopyBaseAgentRunOptions(options, newOptions);
        }

        return newOptions;
    }

#pragma warning disable MEAI001 // ContinuationToken is experimental; copy it through to preserve caller-provided value.
    private static void CopyBaseAgentRunOptions(AgentRunOptions source, AgentRunOptions target)
    {
        target.ContinuationToken = source.ContinuationToken;
        target.AllowBackgroundResponses = source.AllowBackgroundResponses;
        target.AdditionalProperties = source.AdditionalProperties?.Clone();
        target.ResponseFormat = source.ResponseFormat;
    }
#pragma warning restore MEAI001

    /// <summary>The stub <see cref="IChatClient"/> used to delegate from the <see cref="OpenTelemetryChatClient"/> into the inner <see cref="AIAgent"/>.</summary>
    /// <param name="parentAgent"></param>
    private sealed class ForwardingChatClient(OpenTelemetryAgent parentAgent) : IChatClient
    {
        public async Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            ForwardedOptions? fo = options as ForwardedOptions;

            // Update the current activity to reflect the agent invocation.
            parentAgent.UpdateCurrentActivity(fo?.CurrentActivity);

            // If enabled, wire the underlying chat client with OpenTelemetryChatClient via ChatClientFactory.
            var runOptions = parentAgent.GetRunOptionsWithChatClientWiring(fo?.Options);

            // Invoke the inner agent.
            var response = await parentAgent.InnerAgent.RunAsync(messages, fo?.Session, runOptions, cancellationToken).ConfigureAwait(false);

            // Wrap the response in a ChatResponse so we can pass it back through OpenTelemetryChatClient.
            return response.AsChatResponse();
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            ForwardedOptions? fo = options as ForwardedOptions;

            // Update the current activity to reflect the agent invocation.
            parentAgent.UpdateCurrentActivity(fo?.CurrentActivity);

            // If enabled, wire the underlying chat client with OpenTelemetryChatClient via ChatClientFactory.
            var runOptions = parentAgent.GetRunOptionsWithChatClientWiring(fo?.Options);

            // Invoke the inner agent.
            await foreach (var update in parentAgent.InnerAgent.RunStreamingAsync(messages, fo?.Session, runOptions, cancellationToken).ConfigureAwait(false))
            {
                // Wrap the response updates in ChatResponseUpdates so we can pass them back through OpenTelemetryChatClient.
                yield return update.AsChatResponseUpdate();
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            // Delegate any inquiries made by the OpenTelemetryChatClient back to the parent agent.
            parentAgent.GetService(serviceType, serviceKey);

        public void Dispose() { }
    }
}

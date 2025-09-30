﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>Represents a delegating <see cref="AIAgent"/> that implements the OpenTelemetry Semantic Conventions for Generative AI systems.</summary>
/// <remarks>
/// This class provides an implementation of the Semantic Conventions for Generative AI systems, defined at <see href="https://opentelemetry.io/docs/specs/semconv/gen-ai/" />.
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
    // calls back into the inner agent. For state that we can't pass through directly (like AgentRunOptions), we pass that
    // around the OpenTelemetryChatClient via an AsyncLocal.

    /// <summary><see cref="AsyncLocal{ForwardedState}"/> that's used to pass input from this agent into the inner agent.</summary>
    private static readonly AsyncLocal<ForwardedState?> s_forwardedState = new();

    /// <summary>The <see cref="OpenTelemetryChatClient"/> providing the bulk of the telemetry.</summary>
    private readonly OpenTelemetryChatClient _otelClient;
    /// <summary>The provider name extracted from <see cref="AIAgentMetadata"/>.</summary>
    private readonly string? _providerName;

    /// <summary>Initializes a new instance of the <see cref="OpenTelemetryAgent"/> class.</summary>
    /// <param name="innerAgent">The underlying <see cref="AIAgent"/>.</param>
    /// <param name="sourceName">An optional source name that will be used on the telemetry data.</param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    public OpenTelemetryAgent(AIAgent innerAgent, string? sourceName = null) : base(innerAgent)
    {
        this._providerName = innerAgent.GetService<AIAgentMetadata>()?.ProviderName;

        this._otelClient = new OpenTelemetryChatClient(
            new ForwardingChatClient(this),
            sourceName: string.IsNullOrEmpty(sourceName) ? OpenTelemetryConsts.DefaultSourceName : sourceName!);
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
    /// </remarks>
    public bool EnableSensitiveData
    {
        get => this._otelClient.EnableSensitiveData;
        set => this._otelClient.EnableSensitiveData = value;
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        s_forwardedState.Value = new(Activity.Current, thread, options);

        var response = await this._otelClient.GetResponseAsync(messages, (options as ChatClientAgentRunOptions)?.ChatOptions, cancellationToken).ConfigureAwait(false);

        return (AgentRunResponse)response.RawRepresentation!;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        s_forwardedState.Value = new(Activity.Current, thread, options);

        await foreach (var update in this._otelClient.GetStreamingResponseAsync(messages, (options as ChatClientAgentRunOptions)?.ChatOptions, cancellationToken).ConfigureAwait(false))
        {
            yield return (AgentRunResponseUpdate)update.RawRepresentation!;
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

        activity.DisplayName = $"invoke_agent {this.DisplayName}";

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
    private sealed record ForwardedState(
        Activity? CurrentActivity,
        AgentThread? Thread,
        AgentRunOptions? Options);

    /// <summary>The stub <see cref="IChatClient"/> used to delegate from the <see cref="OpenTelemetryChatClient"/> into the inner <see cref="AIAgent"/>.</summary>
    /// <param name="parentAgent"></param>
    private sealed class ForwardingChatClient(OpenTelemetryAgent parentAgent) : IChatClient
    {
        public async Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken)
        {
            // Grab the additional state provided by the parent agent.
            ForwardedState state = s_forwardedState.Value!;

            // Update the current activity to reflect the agent invocation.
            parentAgent.UpdateCurrentActivity(state.CurrentActivity);

            // Invoke the inner agent.
            var response = await parentAgent.InnerAgent.RunAsync(messages, state.Thread, state.Options, cancellationToken).ConfigureAwait(false);

            // Wrap the response in a ChatResponse so we can pass it back through OpenTelemetryChatClient.
            return new ChatResponse
            {
                AdditionalProperties = response.AdditionalProperties,
                CreatedAt = response.CreatedAt,
                Messages = response.Messages,
                RawRepresentation = response,
                ResponseId = response.ResponseId,
                Usage = response.Usage,
            };
        }

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options, [EnumeratorCancellation] CancellationToken cancellationToken)
        {
            // Grab the additional state provided by the parent agent.
            ForwardedState state = s_forwardedState.Value!;

            // Update the current activity to reflect the agent invocation.
            parentAgent.UpdateCurrentActivity(state.CurrentActivity);

            // Invoke the inner agent.
            await foreach (var update in parentAgent.InnerAgent.RunStreamingAsync(messages, state.Thread, state.Options, cancellationToken).ConfigureAwait(false))
            {
                // Wrap the response updates in ChatResponseUpdates so we can pass them back through OpenTelemetryChatClient.
                yield return new ChatResponseUpdate
                {
                    AdditionalProperties = update.AdditionalProperties,
                    AuthorName = update.AuthorName,
                    Contents = update.Contents,
                    CreatedAt = update.CreatedAt,
                    MessageId = update.MessageId,
                    RawRepresentation = update,
                    ResponseId = update.ResponseId,
                    Role = update.Role,
                };
            }
        }

        public object? GetService(Type serviceType, object? serviceKey = null) =>
            // Delegate any inquiries made by the OpenTelemetryChatClient back to the parent agent.
            parentAgent.GetService(serviceType, serviceKey);

        public void Dispose() { }
    }
}

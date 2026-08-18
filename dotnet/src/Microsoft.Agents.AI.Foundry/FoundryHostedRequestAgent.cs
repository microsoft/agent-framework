// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001
#pragma warning disable SCME0001
#pragma warning disable MEAI001

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Delegating agent that applies Foundry hosted-agent request context per run:
/// resolves the sticky hosted-agent session id, injects <c>agent_session_id</c> into the
/// Responses body, stamps <c>x-ms-user-identity</c>, and writes the platform-returned session
/// id back onto the <see cref="AgentSession"/>.
/// </summary>
internal sealed class FoundryHostedRequestAgent : DelegatingAIAgent
{
    public FoundryHostedRequestAgent(AIAgent innerAgent)
        : base(innerAgent)
    {
    }

    /// <inheritdoc/>
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var prepared = Prepare(session, options);
        try
        {
            return await this.InnerAgent.RunAsync(messages, session, prepared.Options, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            // Persist any platform-captured hosted session id even when later agent processing fails.
            ApplySessionSticky(session, prepared.SessionIdBox);
        }
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var prepared = Prepare(session, options);
        try
        {
            await foreach (var update in this.InnerAgent.RunStreamingAsync(messages, session, prepared.Options, cancellationToken).ConfigureAwait(false))
            {
                yield return update;
            }
        }
        finally
        {
            // finally also runs when the consumer disposes the enumerator early.
            ApplySessionSticky(session, prepared.SessionIdBox);
        }
    }

    private static PreparedRun Prepare(AgentSession? session, AgentRunOptions? options)
    {
        ChatOptions? chatOptions = options is ChatClientAgentRunOptions cro ? cro.ChatOptions : null;

        string? sessionHostedId = session?.FoundryHostedAgentSessionId;
        string? optionsHostedId = chatOptions?.GetFoundryHostedAgentSessionId();

        if (!string.IsNullOrWhiteSpace(sessionHostedId)
            && !string.IsNullOrWhiteSpace(optionsHostedId)
            && !string.Equals(sessionHostedId, optionsHostedId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                """
                The hosted-agent session id provided via ChatOptions is different from the id stored on the provided AgentSession.
                Only one hosted-agent session id can be used for a run.
                """);
        }

        string? resolvedHostedId = !string.IsNullOrWhiteSpace(optionsHostedId) ? optionsHostedId : sessionHostedId;
        var sessionIdBox = new StrongBox<string?>(resolvedHostedId);
        HostedSessionIdCaptureScope.Current = sessionIdBox;

        // Always ensure ChatOptions + factory so (a) an existing id is sent on every service call
        // and (b) a platform-created id captured mid-run is sent on later function-loop calls.
        var effectiveOptions = EnsureChatOptions(options, out chatOptions);
        AttachHostedSessionIdFactory(chatOptions, sessionIdBox);

        // Always assign (including null) so a nested Foundry run that omits the per-call Foundry
        // user identity does not inherit a parent AsyncLocal value and stamp the wrong header.
        UserIdentityScope.Current = chatOptions.GetFoundryHostedAgentUserIdentity();

        return new PreparedRun(effectiveOptions, sessionIdBox);
    }

    private static ChatClientAgentRunOptions EnsureChatOptions(AgentRunOptions? options, out ChatOptions chatOptions)
    {
        if (options is ChatClientAgentRunOptions existing)
        {
            // Clone so per-run RawRepresentationFactory wrapping does not mutate caller-owned options
            // or stack factories when the same instance is reused across runs.
            var clone = (ChatClientAgentRunOptions)existing.Clone();
            clone.ChatOptions ??= new ChatOptions();
            chatOptions = clone.ChatOptions;
            return clone;
        }

        chatOptions = new ChatOptions();
        var specialized = new ChatClientAgentRunOptions(chatOptions);
        if (options is not null)
        {
            // Preserve base AgentRunOptions fields when upgrading a plain options instance.
#pragma warning disable MEAI001 // ResponseContinuationToken is experimental
            specialized.ContinuationToken = options.ContinuationToken;
#pragma warning restore MEAI001
            specialized.AllowBackgroundResponses = options.AllowBackgroundResponses;
            specialized.ResponseFormat = options.ResponseFormat;
            specialized.AdditionalProperties = options.AdditionalProperties?.Clone();
        }

        return specialized;
    }

    private static void AttachHostedSessionIdFactory(ChatOptions chatOptions, StrongBox<string?> sessionIdBox)
    {
        var previousFactory = chatOptions.RawRepresentationFactory;
        chatOptions.RawRepresentationFactory = client =>
        {
            object? previous = previousFactory?.Invoke(client);
            if (previous is not null and not CreateResponseOptions)
            {
                return previous;
            }

            var responseOptions = previous as CreateResponseOptions ?? new CreateResponseOptions();
            if (!string.IsNullOrWhiteSpace(sessionIdBox.Value))
            {
                responseOptions.Patch.Set("$.agent_session_id"u8, sessionIdBox.Value);
            }

            return responseOptions;
        };
    }

    private static void ApplySessionSticky(AgentSession? session, StrongBox<string?> sessionIdBox)
    {
        if (session is null || string.IsNullOrWhiteSpace(sessionIdBox.Value))
        {
            return;
        }

        session.FoundryHostedAgentSessionId = sessionIdBox.Value!;
    }

    private sealed class PreparedRun
    {
        public PreparedRun(ChatClientAgentRunOptions options, StrongBox<string?> sessionIdBox)
        {
            this.Options = options;
            this.SessionIdBox = sessionIdBox;
        }

        public ChatClientAgentRunOptions Options { get; }
        public StrongBox<string?> SessionIdBox { get; }
    }
}

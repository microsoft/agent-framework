// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Delegating <see cref="AIAgent"/> that captures any <c>x-client-*</c> headers stored on
/// <see cref="ChatClientAgentRunOptions.ChatOptions"/> by callers of
/// <see cref="ClientHeadersExtensions.WithClientHeader(ChatOptions, string, string)"/> and pushes
/// them onto a <see cref="ClientHeadersScope"/> for the lifetime of the run. The scope is read by
/// <see cref="ClientHeadersPolicy"/> inside the SCM transport pipeline and stamped onto the
/// outbound request.
/// </summary>
/// <remarks>
/// <para>
/// The decorator snapshots the header dictionary at scope-push time so concurrent runs that share
/// the same <see cref="ChatOptions"/> reference are isolated; mutating the source dictionary after
/// <c>RunAsync</c> begins does not leak into in-flight requests.
/// </para>
/// <para>
/// Streaming applies the snapshot before each iterator advancement and disposal. An async iterator
/// resumes in the consumer's execution context, so the scope must be assigned again after each yield.
/// </para>
/// </remarks>
internal sealed class ClientHeadersAgent : DelegatingAIAgent
{
    public ClientHeadersAgent(AIAgent innerAgent)
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
        FoundryFeatureUsage.MarkUsed(FeatureIndex.FoundryAgent);

        // Assign the run's snapshot, including null. The async-method boundary restores the caller's scope.
        ClientHeadersScope.Current = TrySnapshot(options);

        return await this.InnerAgent.RunAsync(messages, session, options, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        FoundryFeatureUsage.MarkUsed(FeatureIndex.FoundryAgent);

        var snapshot = TrySnapshot(options);
        var enumerator = this.InnerAgent
            .RunStreamingAsync(messages, session, options, cancellationToken)
            .GetAsyncEnumerator(cancellationToken);
        try
        {
            while (true)
            {
                ClientHeadersScope.Current = snapshot;
                if (!await enumerator.MoveNextAsync().ConfigureAwait(false))
                {
                    yield break;
                }

                yield return enumerator.Current;
            }
        }
        finally
        {
            ClientHeadersScope.Current = snapshot;
            await enumerator.DisposeAsync().ConfigureAwait(false);
        }
    }

    /// <summary>Reads the header dictionary stamped by <c>WithClientHeader(s)</c> and returns an immutable snapshot, or <see langword="null"/> if none.</summary>
    private static Dictionary<string, string>? TrySnapshot(AgentRunOptions? options)
    {
        if (options is not ChatClientAgentRunOptions { ChatOptions: { } chatOptions })
        {
            return null;
        }

        var headers = chatOptions.GetClientHeaders();
        if (headers is null || headers.Count == 0)
        {
            return null;
        }

        // Copy to defeat caller mutation after RunAsync starts.
        var copy = new Dictionary<string, string>(headers.Count, System.StringComparer.OrdinalIgnoreCase);
        foreach (var kvp in headers)
        {
            copy[kvp.Key] = kvp.Value;
        }

        return copy;
    }
}

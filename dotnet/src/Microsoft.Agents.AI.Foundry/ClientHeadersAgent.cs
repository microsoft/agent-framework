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
/// Streaming uses the async-iterator pattern so the AsyncLocal scope stays alive across yields,
/// which is required because the underlying HTTP send happens during enumeration.
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
        var snapshot = TrySnapshot(options);
        if (snapshot is not null)
        {
            // This method is async, so the runtime restores the caller's ExecutionContext (and
            // therefore the previous ClientHeadersScope.Current value) when the returned task
            // completes. Awaiting the inner call is what establishes that async-method boundary,
            // so the per-run scope set here cannot carry into a later run on the same async flow.
            // See ClientHeadersScope remarks. The streaming path relies on the same behavior.
            ClientHeadersScope.Current = snapshot;
        }

        return await this.InnerAgent.RunAsync(messages, session, options, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var snapshot = TrySnapshot(options);
        if (snapshot is not null)
        {
            ClientHeadersScope.Current = snapshot;
        }

        await foreach (var update in this.InnerAgent.RunStreamingAsync(messages, session, options, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
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

// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Threading;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Carries OAuth consent information for a single tool call that returned JSON-RPC error -32006.
/// </summary>
/// <param name="ToolboxName">The toolbox name that owns the tool.</param>
/// <param name="ToolName">Fully-qualified tool name (e.g., <c>logicapps.send_email</c>).</param>
/// <param name="ConsentUrl">The OAuth consent URL the user must visit.</param>
internal sealed record McpConsentInfo(string ToolboxName, string ToolName, string ConsentUrl);

/// <summary>Function results used when OAuth consent interrupts a tool batch.</summary>
internal static class McpConsentResults
{
    internal const string ConsentRequired = "Error: OAuth consent is required. This tool invocation did not complete. The user must authorize access before this tool can be invoked in a later request.";
    internal const string NotExecuted = "Error: This tool invocation was not executed because another tool requires OAuth consent. The user must authorize access before protected tools can be invoked in a later request.";
}

/// <summary>
/// Per-request mutable state shared between <see cref="ConsentAwareMcpClientAIFunction"/> (child context)
/// and <see cref="AgentFrameworkResponseHandler"/> (parent context) via <see cref="McpConsentContext.Current"/>.
/// </summary>
/// <remarks>
/// Because <see cref="AsyncLocal{T}"/> only flows values DOWN from parent to children,
/// we use a shared reference type so children can mutate it and the parent observes the mutations.
/// </remarks>
internal sealed class RequestConsentState
{
    private readonly ConcurrentQueue<McpConsentInfo> _pendingConsents = new();

    /// <summary>Whether any tool wrapper detected -32006 during this request.</summary>
    internal bool HasPendingConsents => !this._pendingConsents.IsEmpty;

    /// <summary>Adds consent information detected by a tool wrapper.</summary>
    internal void AddPendingConsent(McpConsentInfo consent) => this._pendingConsents.Enqueue(consent);

    /// <summary>Returns a snapshot of every consent requirement detected during this request.</summary>
    internal McpConsentInfo[] GetPendingConsents() => this._pendingConsents.ToArray();

    /// <summary>
    /// Whether the function loop must send its complete result batch back to a downstream service-managed conversation.
    /// </summary>
    internal bool ReconcileDownstreamHistory { get; init; }

    /// <summary>The result returned for other calls skipped after consent is required.</summary>
    internal string InterruptedToolResult { get; init; } = McpConsentResults.NotExecuted;

    /// <summary>The linked CTS for consent handoff outside a function-invoking loop.</summary>
    internal CancellationTokenSource? CancellationSource { get; set; }
}

/// <summary>
/// Async-local context that enables <see cref="ConsentAwareMcpClientAIFunction"/>
/// to signal a consent error back to <see cref="AgentFrameworkResponseHandler"/> through the
/// <see cref="FunctionInvokingChatClient"/> tool loop. Flows with the async ExecutionContext.
/// </summary>
internal static class McpConsentContext
{
    /// <summary>
    /// Holds the shared <see cref="RequestConsentState"/> for the current request.
    /// Bound while advancing or disposing the agent stream; read and mutated by the tool wrapper.
    /// </summary>
    internal static readonly AsyncLocal<RequestConsentState?> Current = new();
}

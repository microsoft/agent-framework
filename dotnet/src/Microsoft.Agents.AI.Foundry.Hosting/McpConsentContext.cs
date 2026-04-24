// Copyright (c) Microsoft. All rights reserved.

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
    /// <summary>Consent information set by the tool wrapper when -32006 is detected.</summary>
    internal McpConsentInfo? Pending { get; set; }

    /// <summary>The linked CTS to cancel when consent is required.</summary>
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
    /// Set once by the handler; read and mutated by the tool wrapper.
    /// </summary>
    internal static readonly AsyncLocal<RequestConsentState?> Current = new();
}

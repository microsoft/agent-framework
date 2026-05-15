// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Resolves the per-request <see cref="HostedSessionContext"/> for a Foundry hosted agent.
/// </summary>
/// <remarks>
/// <para>
/// Implementations are invoked once per incoming Responses API request. The returned
/// <see cref="HostedSessionContext"/> establishes the identity of a freshly created session and
/// is validated against the live request on every subsequent invocation that resumes the same session.
/// </para>
/// <para>
/// The default implementation registered when no custom <see cref="HostedSessionIsolationKeyProvider"/>
/// is present in DI maps the platform-injected <c>x-agent-user-isolation-key</c> and
/// <c>x-agent-chat-isolation-key</c> headers via <see cref="ResponseContext.Isolation"/>. Hosting samples and contributor-only environments
/// can register an alternate implementation in DI to provide values when the platform headers are absent
/// (e.g., during local Docker debugging).
/// </para>
/// <para>
/// Implementations must return a <see cref="HostedSessionContext"/> whose <see cref="HostedSessionContext.UserId"/>
/// and <see cref="HostedSessionContext.ChatId"/> are both non-null and non-whitespace. Returning either as null
/// (or throwing from <see cref="GetKeysAsync"/>) is treated as a configuration error and surfaces as a
/// 500 from the hosting layer.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public abstract class HostedSessionIsolationKeyProvider
{
    /// <summary>
    /// Resolves the <see cref="HostedSessionContext"/> for the supplied request.
    /// </summary>
    /// <param name="context">The per-request <see cref="ResponseContext"/> from the Azure AI Responses Server SDK.</param>
    /// <param name="request">The <see cref="CreateResponse"/> describing the incoming request.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A <see cref="HostedSessionContext"/> with non-null <see cref="HostedSessionContext.UserId"/> and
    /// <see cref="HostedSessionContext.ChatId"/>, or <see langword="null"/> when the implementation cannot
    /// produce identity keys for the current request. A <see langword="null"/> result is treated as a
    /// configuration error by the hosting layer and surfaces as 500.
    /// </returns>
    public abstract ValueTask<HostedSessionContext?> GetKeysAsync(
        ResponseContext context,
        CreateResponse request,
        CancellationToken cancellationToken);
}

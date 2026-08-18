// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Keeps the service behind a hosted agent's chat client from storing the responses it produces, and
/// reports the deployment that ends up storing them anyway.
/// </summary>
/// <remarks>
/// <para>
/// A hosted turn is already recorded by the AgentServer SDK's storage provider, which runs around the
/// handler, and that record is the conversation the caller reads back. A service that also stores the
/// turn writes the same exchange a second time onto a trail of its own, which nothing here reads and
/// no one reconciles with the first.
/// </para>
/// <para>
/// Turning storage off is a container concern, so a deployment that still stores is a server-side
/// misconfiguration rather than a bad request, and is reported as such.
/// </para>
/// </remarks>
internal static class HostedStoredOutputCompatibility
{
    /// <summary>
    /// HTTP status returned when the agent's own service stored the turn. <c>501 Not Implemented</c>
    /// is a server-side classification, because the deployment, not the caller, is misconfigured; it is
    /// also non-retryable and distinct from the generic <c>500</c> so it stands out in telemetry.
    /// </summary>
    internal const int MisconfiguredAgentStatusCode = 501;

    /// <summary>
    /// Stable error code emitted in the response body so callers and tooling can match the condition.
    /// </summary>
    internal const string MisconfiguredAgentErrorCode = "agent_stored_output_not_disabled";

    /// <summary>
    /// Returns the error to throw when the agent's own service kept the turn.
    /// </summary>
    internal static ResponsesApiException CreateMisconfiguredAgentError() =>
        new(
            new Error(
                MisconfiguredAgentErrorCode,
                "The agent should not have server side storage enabled. This produced a new untracked conversation/response in the server while the hosted agent also generated a conversation for the request of the agent. This setting is only allowed when enabling the FoundryResponsesOptions.AllowStoredOutputEnabled flag, which leaves the agent's own storage setting untouched and keeps that second recording on purpose."),
            MisconfiguredAgentStatusCode);
}

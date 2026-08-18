// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Detects when this image, which targets the Foundry Responses container protocol <c>2.0.0</c>,
/// is being served the older <c>1.0.0</c> protocol, and turns that mismatch into a clear, actionable
/// error instead of an opaque <c>500</c> on every request.
/// </summary>
/// <remarks>
/// <para>
/// The container has no startup signal for its negotiated protocol version: the platform injects the
/// agent identity (<c>FOUNDRY_AGENT_NAME</c>/<c>FOUNDRY_AGENT_VERSION</c>) and a hosted flag
/// (<c>FOUNDRY_HOSTING_ENVIRONMENT</c>), but not the responses protocol version, and
/// <c>container_protocol_versions</c> is a control-plane field on the agent definition that is never
/// passed into the image. The only per-request signal is the presence of the
/// <c>x-agent-foundry-call-id</c> header, which the platform sends exclusively on protocol
/// <c>2.0.0</c>.
/// </para>
/// <para>
/// Therefore, when the container is hosted by Foundry yet receives no call id, the platform is talking
/// <c>1.0.0</c> to a <c>2.0.0</c>-only image. That is a server-side deployment misconfiguration, so the
/// failure is surfaced as a <c>5xx</c> (<see cref="UnsupportedProtocolStatusCode"/>) whose body names
/// both the cause and the fix.
/// </para>
/// </remarks>
internal static class HostedProtocolCompatibility
{
    /// <summary>
    /// HTTP status returned when this image is served a container protocol version it does not support.
    /// <c>501 Not Implemented</c> is a server-side (<c>5xx</c>) classification, because the deployment,
    /// not the caller, is misconfigured; it is also non-retryable and distinct from the generic
    /// <c>500</c> so it stands out in platform telemetry.
    /// </summary>
    internal const int UnsupportedProtocolStatusCode = 501;

    /// <summary>
    /// Stable error code emitted in the response body so callers and tooling can match the condition.
    /// </summary>
    internal const string UnsupportedProtocolErrorCode = "unsupported_container_protocol_version";

    /// <summary>
    /// Returns the error to throw when this <c>2.0.0</c>-only image is served container protocol
    /// <c>1.0.0</c>, or <see langword="null"/> when the request is compatible (or the container is not
    /// hosted by Foundry, e.g. local development).
    /// </summary>
    /// <param name="isHosted">
    /// Whether the container is running inside Foundry, from <c>FoundryEnvironment.IsHosted</c>
    /// (<c>FOUNDRY_HOSTING_ENVIRONMENT</c>). Local (non-hosted) runs are never flagged.
    /// </param>
    /// <param name="callId">
    /// The per-request <c>x-agent-foundry-call-id</c> value (protocol <c>2.0.0</c> only). Absence while
    /// hosted indicates a <c>1.0.0</c> deployment.
    /// </param>
    /// <returns>
    /// A <see cref="ResponsesApiException"/> carrying <see cref="UnsupportedProtocolStatusCode"/> and a
    /// clear message, or <see langword="null"/> when the request is compatible.
    /// </returns>
    internal static ResponsesApiException? GetUnsupportedProtocolError(bool isHosted, string? callId)
    {
        if (!isHosted || !string.IsNullOrWhiteSpace(callId))
        {
            return null;
        }

        return new ResponsesApiException(
            new Error(
                UnsupportedProtocolErrorCode,
                "Unsupported responses protocol version. This agent requires responses protocol v2.0.0"),
            UnsupportedProtocolStatusCode);
    }
}

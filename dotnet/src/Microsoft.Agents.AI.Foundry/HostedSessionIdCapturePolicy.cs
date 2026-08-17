// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Pipeline policy that captures the <c>x-agent-session-id</c> response header into
/// <see cref="HostedSessionIdCaptureScope"/> so subsequent service calls in the same run (and the
/// session sticky update after the run) see the platform-assigned hosted-agent session id.
/// </summary>
/// <remarks>
/// When the scope already holds a pinned id, a different response id is rejected as an unexpected
/// Foundry hosted session switch rather than silently overwriting the sticky value.
/// </remarks>
internal sealed class HostedSessionIdCapturePolicy : PipelinePolicy
{
    internal const string SessionIdHeader = "x-agent-session-id";

    public static HostedSessionIdCapturePolicy Instance { get; } = new HostedSessionIdCapturePolicy();

    private HostedSessionIdCapturePolicy()
    {
    }

    public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        ProcessNext(message, pipeline, currentIndex);
        Capture(message);
    }

    public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
    {
        await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
        Capture(message);
    }

    private static void Capture(PipelineMessage message)
    {
        if (message.Response is null)
        {
            return;
        }

        if (HostedSessionIdCaptureScope.Current is not { } box)
        {
            return;
        }

        if (message.Response.Headers.TryGetValue(SessionIdHeader, out string? sessionId)
            && !string.IsNullOrWhiteSpace(sessionId))
        {
            sessionId = sessionId.Trim();
            if (!string.IsNullOrWhiteSpace(box.Value)
                && !string.Equals(box.Value, sessionId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"Unexpected Foundry hosted session switch. The run is pinned to hosted session '{box.Value}' " +
                    $"but the response returned '{sessionId}'.");
            }

            box.Value = sessionId;
        }
    }
}

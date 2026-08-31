// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="HostedProtocolCompatibility"/>, the protocol-version gate that turns an
/// opaque 500 into a clear 501 when this 2.0.0-only image is served container protocol 1.0.0.
/// </summary>
public sealed class HostedProtocolCompatibilityTests
{
    [Fact]
    public void GetUnsupportedProtocolError_HostedWithoutCallId_ReturnsUnsupportedProtocolError()
    {
        // Hosted by Foundry (FoundryEnvironment.IsHosted == true) but no x-agent-foundry-call-id header
        // means the platform is talking protocol 1.0.0 to a 2.0.0-only image.
        ResponsesApiException? error = HostedProtocolCompatibility.GetUnsupportedProtocolError(isHosted: true, callId: null);

        Assert.NotNull(error);
        Assert.Equal(HostedProtocolCompatibility.UnsupportedProtocolStatusCode, error!.StatusCode);
        Assert.Equal(501, error.StatusCode);
        Assert.Equal(HostedProtocolCompatibility.UnsupportedProtocolErrorCode, error.Error.Code);
        Assert.Equal("Unsupported responses protocol version. This agent requires responses protocol v2.0.0", error.Error.Message);
    }

    [Fact]
    public void GetUnsupportedProtocolError_HostedWithEmptyCallId_ReturnsUnsupportedProtocolError()
    {
        // An empty or whitespace-only header value is treated the same as an absent one, so a proxy that
        // injects whitespace cannot bypass the gate.
        foreach (var callId in new[] { "", "   ", "\t" })
        {
            ResponsesApiException? error = HostedProtocolCompatibility.GetUnsupportedProtocolError(isHosted: true, callId: callId);

            Assert.NotNull(error);
            Assert.Equal(501, error!.StatusCode);
            Assert.Equal(HostedProtocolCompatibility.UnsupportedProtocolErrorCode, error.Error.Code);
        }
    }

    [Fact]
    public void GetUnsupportedProtocolError_HostedWithCallId_ReturnsNull()
    {
        // Protocol 2.0.0: the platform supplies x-agent-foundry-call-id, so the request is compatible.
        ResponsesApiException? error = HostedProtocolCompatibility.GetUnsupportedProtocolError(isHosted: true, callId: "fcid_abc123");

        Assert.Null(error);
    }

    [Fact]
    public void GetUnsupportedProtocolError_NotHosted_ReturnsNull()
    {
        // Local development (not hosted by Foundry) is never flagged, regardless of the call id.
        Assert.Null(HostedProtocolCompatibility.GetUnsupportedProtocolError(isHosted: false, callId: null));
        Assert.Null(HostedProtocolCompatibility.GetUnsupportedProtocolError(isHosted: false, callId: "fcid_abc123"));
    }
}

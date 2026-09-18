// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Provokes the protocol-compatibility failure on purpose: the test container (which targets responses
/// protocol <c>2.0.0</c> only) is deployed under responses protocol <c>1.0.0</c>. Invoking it must
/// surface the clear <c>501</c> error the container emits (see <c>HostedProtocolCompatibility</c>),
/// rather than an opaque 500.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class UnsupportedProtocolHostedAgentTests(UnsupportedProtocolHostedAgentFixture fixture) : IClassFixture<UnsupportedProtocolHostedAgentFixture>
{
    private readonly UnsupportedProtocolHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task RunAsync_OnProtocol1_0_0_FailsWith501UnsupportedProtocolAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act: a 1.0.0 deployment sends no x-agent-foundry-call-id header, so the container detects the
        // unsupported protocol and fails fast. The OpenAI responses client surfaces the container's HTTP
        // error as a ClientResultException.
        var ex = await Assert.ThrowsAnyAsync<Exception>(() => agent.RunAsync("Reply with a short greeting."));

        // Assert: the failure is the deliberate 501, not an opaque 500, and the body names the required
        // protocol so the operator knows the fix.
        var clientError = FindClientResultException(ex);
        Assert.NotNull(clientError);
        Assert.Equal(501, clientError!.Status);
        Assert.Contains("2.0.0", clientError.Message, StringComparison.OrdinalIgnoreCase);
    }

    private static ClientResultException? FindClientResultException(Exception? ex)
    {
        for (var current = ex; current is not null; current = current.InnerException)
        {
            if (current is ClientResultException clientResultException)
            {
                return clientResultException;
            }
        }

        return null;
    }
}

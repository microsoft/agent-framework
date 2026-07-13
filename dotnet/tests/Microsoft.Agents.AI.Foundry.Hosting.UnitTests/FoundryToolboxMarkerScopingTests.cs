// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Verifies that resolving a per-request toolbox marker via
/// <see cref="FoundryToolboxService.GetToolboxToolsAsync"/> is strictly request-scoped: a marker
/// referenced by one request must never leak its tools into — or raise a consent prompt on — a
/// request that did not reference it, and must not flip the container-global startup state.
/// </summary>
[Collection(FoundryProjectEndpointEnvFixture.Name)]
public class FoundryToolboxMarkerScopingTests
{
    private static async Task<FoundryToolboxService> CreateStartedServiceAsync(
        Func<string, string?, CancellationToken, Task<FoundryToolboxService.ToolboxOpenResult>> opener)
    {
        // Non-strict, no pre-registered toolboxes: StartAsync only resolves the endpoint (so the
        // marker path can run) and reports Healthy. The opener seam replaces the network I/O.
        var options = new FoundryToolboxOptions
        {
            StrictMode = false,
            EndpointOverride = "http://127.0.0.1:1/unused",
        };

        var service = new FoundryToolboxService(
            Options.Create(options),
            Mock.Of<TokenCredential>())
        {
            ToolboxOpener = opener,
        };

        await service.StartAsync(CancellationToken.None);

        // Sanity: a clean start with no pre-registered toolboxes is Healthy and global-empty.
        Assert.Equal(FoundryToolboxStartupStatus.Healthy, service.StartupStatus);
        Assert.Empty(service.ConsentRequiredToolboxNames);
        Assert.Empty(service.Tools);

        return service;
    }

    [Fact]
    public async Task GetToolboxToolsAsync_MarkerConsent_IsRequestScopedAndDoesNotMutateGlobalStateAsync()
    {
        // Arrange: the opener reports CONSENT_REQUIRED for every marker.
        await using var service = await CreateStartedServiceAsync(
            (name, _, _) => Task.FromResult(
                new FoundryToolboxService.ToolboxOpenResult(
                    Cached: null,
                    Consents: [new McpConsentInfo(name, $"{name}.tool", $"https://consent.example/{name}")])));

        // Act: request A references marker-a and hits consent.
        var resolutionA = await service.GetToolboxToolsAsync("marker-a", version: null, CancellationToken.None);

        // Assert: the consent is returned to THIS caller, with no tools.
        Assert.Empty(resolutionA.Tools);
        Assert.Single(resolutionA.Consents);
        Assert.Equal("https://consent.example/marker-a", resolutionA.Consents[0].ConsentUrl);

        // Assert: container-global state is unchanged. The marker consent did not get recorded in
        // ConsentRequiredToolboxNames and did not flip StartupStatus to ConsentRequired, so a request
        // with no marker (which reads StartupStatus / Tools) is unaffected.
        Assert.Equal(FoundryToolboxStartupStatus.Healthy, service.StartupStatus);
        Assert.Empty(service.ConsentRequiredToolboxNames);
        Assert.Empty(service.Tools);

        // Act: a different request references marker-b. Its consent must not accumulate globally.
        var resolutionB = await service.GetToolboxToolsAsync("marker-b", version: null, CancellationToken.None);

        // Assert: still request-scoped, still no global mutation.
        Assert.Single(resolutionB.Consents);
        Assert.Equal("https://consent.example/marker-b", resolutionB.Consents[0].ConsentUrl);
        Assert.Equal(FoundryToolboxStartupStatus.Healthy, service.StartupStatus);
        Assert.Empty(service.ConsentRequiredToolboxNames);
        Assert.Empty(service.Tools);
    }

    [Fact]
    public async Task GetToolboxToolsAsync_MarkerTools_AreReturnedToCallerNotInjectedGloballyAsync()
    {
        // Arrange: the opener resolves marker-a to one tool; any other marker stays consent-gated.
        AITool markerTool = AIFunctionFactory.Create(() => "ok", name: "marker_a_tool");

        await using var service = await CreateStartedServiceAsync(
            (name, _, _) => Task.FromResult(
                string.Equals(name, "marker-a", StringComparison.OrdinalIgnoreCase)
                    ? new FoundryToolboxService.ToolboxOpenResult(
                        new FoundryToolboxService.CachedToolbox(Client: null, new HttpClient(), [markerTool]),
                        Consents: null)
                    : new FoundryToolboxService.ToolboxOpenResult(
                        Cached: null,
                        Consents: [new McpConsentInfo(name, $"{name}.tool", $"https://consent.example/{name}")])));

        // Act: request A references marker-a and resolves its tool.
        var resolutionA = await service.GetToolboxToolsAsync("marker-a", version: null, CancellationToken.None);

        // Assert: the tool is returned to THIS caller only.
        Assert.Empty(resolutionA.Consents);
        Assert.Single(resolutionA.Tools);
        Assert.Same(markerTool, resolutionA.Tools[0]);

        // Assert: the resolved marker tool was NOT merged into the service-wide Tools cache, so a
        // later request with no marker (which only ever gets _toolboxService.Tools) sees nothing.
        Assert.Empty(service.Tools);

        // Act: re-resolving marker-a returns the cached tool (no second open), still request-scoped.
        var resolutionAgain = await service.GetToolboxToolsAsync("marker-a", version: null, CancellationToken.None);

        // Assert.
        Assert.Single(resolutionAgain.Tools);
        Assert.Same(markerTool, resolutionAgain.Tools[0]);
        Assert.Empty(service.Tools);
    }
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[Collection(FoundryProjectEndpointEnvFixture.Name)]
public class FoundryToolboxServiceTests
{
    [Fact]
    public async Task GetToolboxToolsAsync_StrictMode_ThrowsForUnknownToolboxAsync()
    {
        var options = new FoundryToolboxOptions { StrictMode = true };
        var service = new FoundryToolboxService(
            Options.Create(options),
            Mock.Of<TokenCredential>());

        // Act + Assert: no StartAsync so Tools is empty; unknown name in strict mode throws.
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await service.GetToolboxToolsAsync("missing", version: null, CancellationToken.None));

        Assert.Contains("missing", ex.Message, StringComparison.Ordinal);
        Assert.Contains("StrictMode", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetToolboxToolsAsync_NonStrictMode_RequiresEndpointAsync()
    {
        var options = new FoundryToolboxOptions { StrictMode = false };
        var service = new FoundryToolboxService(
            Options.Create(options),
            Mock.Of<TokenCredential>());

        // Without calling StartAsync, endpoint is not resolved so lazy-open fails clearly.
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await service.GetToolboxToolsAsync("missing", version: null, CancellationToken.None));

        Assert.Contains("FOUNDRY_PROJECT_ENDPOINT", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task StartAsync_WithoutEndpoint_LeavesToolsEmptyAsync()
    {
        // Ensure neither env var is set (tests may run in any CI environment)
        var savedFoundry = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        var savedAzure = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", null);
        Environment.SetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT", null);
        try
        {
            var options = new FoundryToolboxOptions();
            options.ToolboxNames.Add("any");
            var service = new FoundryToolboxService(
                Options.Create(options),
                Mock.Of<TokenCredential>());

            await service.StartAsync(CancellationToken.None);

            Assert.Empty(service.Tools);
            Assert.Equal(FoundryToolboxStartupStatus.NoEndpoint, service.StartupStatus);
            Assert.Empty(service.FailedToolboxNames);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", savedFoundry);
            Environment.SetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT", savedAzure);
        }
    }

    [Fact]
    public async Task StartAsync_AttemptsOpenForPreRegisteredToolboxFromProjectEndpointAsync()
    {
        // Arrange: point the service at an unreachable host and confirm StartAsync
        // attempts to open the pre-registered toolbox (verified via DeferredToolboxNames
        // recording the attempted name and StartupStatus reflecting the deferral).
        var saved = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable(
            "FOUNDRY_PROJECT_ENDPOINT",
            "https://example.invalid/api/projects/proj");
        try
        {
            var options = new FoundryToolboxOptions { ApiVersion = "v1" };
            options.ToolboxNames.Add("my-toolbox");
            var service = new FoundryToolboxService(
                Options.Create(options),
                Mock.Of<TokenCredential>());

            // Act: StartAsync attempts to connect to the invalid endpoint and fails.
            // The failure path defers the toolbox; the recorded name confirms the resolver ran.
            await service.StartAsync(CancellationToken.None);

            // Assert: open failed but the container stays routable (deferred, not bricked), and
            // the deferred name matches — i.e. we attempted the right toolbox.
            Assert.Equal(FoundryToolboxStartupStatus.Degraded, service.StartupStatus);
            Assert.Empty(service.FailedToolboxNames);
            Assert.Single(service.DeferredToolboxNames);
            Assert.Equal("my-toolbox", service.DeferredToolboxNames[0]);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", saved);
        }
    }

    [Fact]
    public async Task StartAsync_TrailingSlashOnProjectEndpoint_AttemptsOpenAsync()
    {
        var saved = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable(
            "FOUNDRY_PROJECT_ENDPOINT",
            "https://example.invalid/api/projects/proj/");
        try
        {
            var options = new FoundryToolboxOptions();
            options.ToolboxNames.Add("tb");
            var service = new FoundryToolboxService(
                Options.Create(options),
                Mock.Of<TokenCredential>());

            await service.StartAsync(CancellationToken.None);

            // Arrange/Act: when trailing-slash normalization works the open still fails
            // (host is unreachable), but DeferredToolboxNames records the attempted name —
            // proof that the resolver did not throw on the slash and the URL was built.
            Assert.Equal(FoundryToolboxStartupStatus.Degraded, service.StartupStatus);
            Assert.Single(service.DeferredToolboxNames);
            Assert.Equal("tb", service.DeferredToolboxNames[0]);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", saved);
        }
    }

    [Fact]
    public async Task StartAsync_EndpointOverrideWinsOverEnvAsync()
    {
        var saved = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable(
            "FOUNDRY_PROJECT_ENDPOINT",
            "https://from-env.invalid/api/projects/proj");
        try
        {
            // EndpointOverride should take precedence over the env var.
            var options = new FoundryToolboxOptions
            {
                EndpointOverride = "http://127.0.0.1:1/from-override",
            };
            options.ToolboxNames.Add("tb");

            var service = new FoundryToolboxService(
                Options.Create(options),
                Mock.Of<TokenCredential>());

            await service.StartAsync(CancellationToken.None);

            // Override URL is unreachable; we expect Degraded (proving Start did try to open
            // a toolbox, i.e. did not fall into the NoEndpoint branch) while staying routable.
            Assert.Equal(FoundryToolboxStartupStatus.Degraded, service.StartupStatus);
            Assert.Single(service.DeferredToolboxNames);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", saved);
        }
    }

    [Fact]
    public async Task StartAsync_WithEndpointButFailingToolbox_RecordsFailureAndStaysReachableAsync()
    {
        // Arrange: a syntactically valid but unreachable endpoint forces OpenToolboxAsync
        // to throw inside the catch-and-defer path. The service must still complete StartAsync
        // (so the host doesn't crash) and keep the container routable, deferring the toolbox to
        // per-request resolution rather than failing readiness.
        var options = new FoundryToolboxOptions
        {
            EndpointOverride = "http://127.0.0.1:1/unreachable",
        };
        options.ToolboxNames.Add("broken-toolbox");

        var service = new FoundryToolboxService(
            Options.Create(options),
            Mock.Of<TokenCredential>());

        // Act
        await service.StartAsync(CancellationToken.None);

        // Assert
        Assert.Equal(FoundryToolboxStartupStatus.Degraded, service.StartupStatus);
        Assert.Empty(service.FailedToolboxNames);
        Assert.Single(service.DeferredToolboxNames);
        Assert.Equal("broken-toolbox", service.DeferredToolboxNames[0]);
        Assert.Empty(service.Tools);

        // A deferred (non-consent) toolbox is not a consent requirement: ConsentRequiredToolboxNames
        // must stay empty. RecomputeStatus is the single source that keeps ConsentRequiredToolboxNames
        // in sync with the pending-consent set, so they never diverge.
        Assert.Empty(service.ConsentRequiredToolboxNames);
    }

    [Fact]
    public async Task RetryDeferredToolboxesAsync_StillUnreachable_StaysDeferredAndRoutableAsync()
    {
        // Arrange: a deferred toolbox (open failed at startup against an unreachable endpoint).
        // A per-request retry that still cannot reach the proxy must keep the toolbox deferred
        // and the container routable (Degraded), never throwing into the request pipeline.
        var options = new FoundryToolboxOptions
        {
            EndpointOverride = "http://127.0.0.1:1/unreachable",
        };
        options.ToolboxNames.Add("broken-toolbox");

        var service = new FoundryToolboxService(
            Options.Create(options),
            Mock.Of<TokenCredential>());

        await service.StartAsync(CancellationToken.None);
        Assert.Single(service.DeferredToolboxNames);

        // Act: retry while the endpoint is still unreachable.
        await service.RetryDeferredToolboxesAsync(CancellationToken.None);

        // Assert: unchanged — still deferred, still routable, no tools injected.
        Assert.Equal(FoundryToolboxStartupStatus.Degraded, service.StartupStatus);
        Assert.Single(service.DeferredToolboxNames);
        Assert.Equal("broken-toolbox", service.DeferredToolboxNames[0]);
        Assert.Empty(service.FailedToolboxNames);
        Assert.Empty(service.Tools);
    }

    [Fact]
    public async Task StartAsync_WithEndpointAndNoToolboxes_ReportsHealthyAsync()
    {
        // No pre-registered toolboxes is a legitimate "lazy-only" setup. Health-check
        // should report Healthy so the readiness probe passes.
        var options = new FoundryToolboxOptions
        {
            EndpointOverride = "http://127.0.0.1:1/unused",
        };

        var service = new FoundryToolboxService(
            Options.Create(options),
            Mock.Of<TokenCredential>());

        await service.StartAsync(CancellationToken.None);

        Assert.Equal(FoundryToolboxStartupStatus.Healthy, service.StartupStatus);
        Assert.Empty(service.FailedToolboxNames);
        Assert.Empty(service.Tools);
    }
}

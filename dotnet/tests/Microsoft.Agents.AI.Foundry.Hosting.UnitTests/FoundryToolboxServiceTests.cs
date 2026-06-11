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
        // attempts to open the pre-registered toolbox (verified via FailedToolboxNames
        // recording the attempted name and StartupStatus reflecting the failure).
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
            // The failure path records FailedToolboxNames; the value confirms the resolver ran.
            await service.StartAsync(CancellationToken.None);

            // Assert: open failed, status reflects that (resolver was reached), and
            // the failed name matches — i.e. we attempted the right toolbox.
            Assert.Equal(FoundryToolboxStartupStatus.Unhealthy, service.StartupStatus);
            Assert.Single(service.FailedToolboxNames);
            Assert.Equal("my-toolbox", service.FailedToolboxNames[0]);
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
            // (host is unreachable), but FailedToolboxNames records the attempted name —
            // proof that the resolver did not throw on the slash and the URL was built.
            Assert.Equal(FoundryToolboxStartupStatus.Unhealthy, service.StartupStatus);
            Assert.Single(service.FailedToolboxNames);
            Assert.Equal("tb", service.FailedToolboxNames[0]);
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

            // Override URL is unreachable; we expect Unhealthy (proving Start did try to open
            // a toolbox, i.e. did not fall into the NoEndpoint branch).
            Assert.Equal(FoundryToolboxStartupStatus.Unhealthy, service.StartupStatus);
            Assert.Single(service.FailedToolboxNames);
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
        // to throw inside the catch-and-log path. The service must still complete StartAsync
        // (so the host doesn't crash) and surface the failure via StartupStatus.
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
        Assert.Equal(FoundryToolboxStartupStatus.Unhealthy, service.StartupStatus);
        Assert.Single(service.FailedToolboxNames);
        Assert.Equal("broken-toolbox", service.FailedToolboxNames[0]);
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

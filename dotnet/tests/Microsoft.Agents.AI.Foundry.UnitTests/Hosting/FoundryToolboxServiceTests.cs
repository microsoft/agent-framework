// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

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

        Assert.Contains("FOUNDRY_AGENT_TOOLSET_ENDPOINT", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task StartAsync_WithoutEndpoint_LeavesToolsEmptyAsync()
    {
        // Ensure env var is not set (tests may run in any CI environment)
        var saved = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_ENDPOINT");
        Environment.SetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_ENDPOINT", null);
        try
        {
            var options = new FoundryToolboxOptions();
            options.ToolboxNames.Add("any");
            var service = new FoundryToolboxService(
                Options.Create(options),
                Mock.Of<TokenCredential>());

            await service.StartAsync(CancellationToken.None);

            Assert.Empty(service.Tools);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_ENDPOINT", saved);
        }
    }
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

[Collection(FoundryProjectEndpointEnvFixture.Name)]
public class FoundryToolboxHealthCheckTests
{
    [Fact]
    public async Task CheckHealthAsync_PendingStatus_ReturnsConfiguredFailureAsync()
    {
        // Arrange: a fresh FoundryToolboxService whose StartAsync has never run reports
        // Pending. The health check must surface that as the registration's failure
        // status so the platform waits before sending traffic.
        var service = CreateServiceWithoutStarting();
        var check = new FoundryToolboxHealthCheck(service);
        var context = NewContext(failureStatus: HealthStatus.Unhealthy);

        // Act
        var result = await check.CheckHealthAsync(context);

        // Assert
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Contains("startup has not completed", result.Description, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CheckHealthAsync_NoEndpointStatus_ReturnsHealthyAsync()
    {
        // Arrange: no FOUNDRY_PROJECT_ENDPOINT / AZURE_AI_PROJECT_ENDPOINT is normal local-dev.
        // The container must still pass readiness because the rest of the agent is functional.
        var savedFoundry = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
        var savedAzure = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT");
        Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", null);
        Environment.SetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT", null);
        try
        {
            var service = CreateServiceWithoutStarting(toolbox: "any");
            await service.StartAsync(CancellationToken.None);

            var check = new FoundryToolboxHealthCheck(service);
            var context = NewContext(failureStatus: HealthStatus.Unhealthy);

            // Act
            var result = await check.CheckHealthAsync(context);

            // Assert
            Assert.Equal(HealthStatus.Healthy, result.Status);
            Assert.Equal(FoundryToolboxStartupStatus.NoEndpoint, service.StartupStatus);
        }
        finally
        {
            Environment.SetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT", savedFoundry);
            Environment.SetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT", savedAzure);
        }
    }

    [Fact]
    public async Task CheckHealthAsync_DegradedStatus_StaysRoutableForDeferredToolboxAsync()
    {
        // Arrange: a pre-registered toolbox at an unreachable endpoint forces StartAsync to defer
        // the toolbox (non-consent failure). The container must stay routable so the toolbox can be
        // retried per-request, where the platform injects the per-user isolation key on egress.
        var options = new FoundryToolboxOptions
        {
            EndpointOverride = "http://127.0.0.1:1/unreachable",
        };
        options.ToolboxNames.Add("broken-toolbox");
        var service = new FoundryToolboxService(Options.Create(options), Mock.Of<TokenCredential>());
        await service.StartAsync(CancellationToken.None);

        var check = new FoundryToolboxHealthCheck(service);
        var context = NewContext(failureStatus: HealthStatus.Unhealthy);

        // Act
        var result = await check.CheckHealthAsync(context);

        // Assert: deferred toolbox keeps the container Healthy (routable), not bricked.
        Assert.Equal(FoundryToolboxStartupStatus.Degraded, service.StartupStatus);
        Assert.Equal(HealthStatus.Healthy, result.Status);
        Assert.Equal("broken-toolbox", Assert.Single(service.DeferredToolboxNames));
        Assert.Contains("deferred", result.Description, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CheckHealthAsync_HealthyStatus_ReturnsHealthyAsync()
    {
        // Arrange: an endpoint set but no pre-registered toolboxes is the legitimate
        // lazy-only setup. StartAsync reports Healthy and the check must agree.
        var options = new FoundryToolboxOptions
        {
            EndpointOverride = "http://127.0.0.1:1/unused",
        };
        var service = new FoundryToolboxService(Options.Create(options), Mock.Of<TokenCredential>());
        await service.StartAsync(CancellationToken.None);

        var check = new FoundryToolboxHealthCheck(service);
        var context = NewContext(failureStatus: HealthStatus.Unhealthy);

        // Act
        var result = await check.CheckHealthAsync(context);

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    private static FoundryToolboxService CreateServiceWithoutStarting(string? toolbox = null)
    {
        var options = new FoundryToolboxOptions();
        if (toolbox is not null)
        {
            options.ToolboxNames.Add(toolbox);
        }
        return new FoundryToolboxService(Options.Create(options), Mock.Of<TokenCredential>());
    }

    private static HealthCheckContext NewContext(HealthStatus failureStatus) =>
        new()
        {
            Registration = new HealthCheckRegistration(
                name: "foundry-toolbox",
                instance: Mock.Of<IHealthCheck>(),
                failureStatus: failureStatus,
                tags: null),
        };
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public class AgentRegistrationHealthCheckTests
{
    [Fact]
    public async Task CheckHealthAsync_AgentPresent_ReturnsHealthyAsync()
    {
        // Arrange: the predicate reports an agent is registered (default or keyed).
        var check = new AgentRegistrationHealthCheck(() => true);

        // Act
        var result = await check.CheckHealthAsync(NewContext(HealthStatus.Unhealthy));

        // Assert
        Assert.Equal(HealthStatus.Healthy, result.Status);
    }

    [Fact]
    public async Task CheckHealthAsync_NoAgent_ReturnsConfiguredFailureAsync()
    {
        // Arrange: the predicate reports no agent registered.
        var check = new AgentRegistrationHealthCheck(() => false);

        // Act
        var result = await check.CheckHealthAsync(NewContext(HealthStatus.Unhealthy));

        // Assert
        Assert.Equal(HealthStatus.Unhealthy, result.Status);
        Assert.Contains("no AIAgent is registered", result.Description, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void DescriptorPredicate_DetectsKeyedAndDefaultAgents()
    {
        // Guards the descriptor-based detection the registration wires in: both a default and a
        // keyed AIAgent registration expose ServiceType == typeof(AIAgent).
        var keyed = new ServiceCollection();
        keyed.AddKeyedSingleton("my-agent", new Mock<AIAgent>().Object);
        Assert.Contains(keyed, d => d.ServiceType == typeof(AIAgent));

        var byDefault = new ServiceCollection();
        byDefault.AddSingleton(new Mock<AIAgent>().Object);
        Assert.Contains(byDefault, d => d.ServiceType == typeof(AIAgent));

        var empty = new ServiceCollection();
        Assert.DoesNotContain(empty, d => d.ServiceType == typeof(AIAgent));
    }

    private static HealthCheckContext NewContext(HealthStatus failureStatus) =>
        new()
        {
            Registration = new HealthCheckRegistration(
                name: "foundry-agent-registration",
                instance: Mock.Of<IHealthCheck>(),
                failureStatus: failureStatus,
                tags: null),
        };
}

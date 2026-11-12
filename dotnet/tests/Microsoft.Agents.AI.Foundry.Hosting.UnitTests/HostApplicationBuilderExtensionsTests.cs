// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class HostApplicationBuilderExtensionsTests
{
    [Fact]
    public void AddFoundryResponses_OptionsObject_UsesAgentServerDefaultsOverHostSettings()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();
        builder.Configuration[$"ResponsesServer:{nameof(FoundryResponsesServerOptions.ResilientBackground)}"] = "true";

        // Act
        builder.AddFoundryResponses(Mock.Of<AIAgent>(), options: new FoundryResponsesServerOptions
        {
            InferenceStoredOutputAllowed = true,
        });
        using ServiceProvider provider = builder.Services.BuildServiceProvider();
        FoundryResponsesServerOptions registeredOptions =
            provider.GetRequiredService<IOptions<FoundryResponsesServerOptions>>().Value;

        // Assert
        Assert.True(registeredOptions.InferenceStoredOutputAllowed);
        Assert.False(registeredOptions.ResilientBackground);
    }

    [Fact]
    public void AddFoundryResponses_OptionsObject_ExplicitFalseOverridesHostSettings()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();
        builder.Configuration[$"ResponsesServer:{nameof(FoundryResponsesServerOptions.ResilientBackground)}"] = "true";

        // Act
        builder.AddFoundryResponses(Mock.Of<AIAgent>(), options: new FoundryResponsesServerOptions
        {
            ResilientBackground = false,
        });
        using ServiceProvider provider = builder.Services.BuildServiceProvider();

        // Assert
        Assert.False(
            provider.GetRequiredService<IOptions<FoundryResponsesServerOptions>>()
                .Value.ResilientBackground);
    }

    [Fact]
    public void AddFoundryResponses_CalledTwice_Throws()
    {
        // Arrange: a container serves exactly one agent.
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();
        builder.AddFoundryResponses(Mock.Of<AIAgent>());

        // Act and assert
        var exception = Assert.Throws<InvalidOperationException>(
            () => builder.AddFoundryResponses(_ => Mock.Of<AIAgent>(), ServiceLifetime.Scoped));
        Assert.Contains("exactly one agent", exception.Message, StringComparison.Ordinal);
    }
}

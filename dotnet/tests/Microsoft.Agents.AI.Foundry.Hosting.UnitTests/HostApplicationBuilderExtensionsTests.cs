// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class HostApplicationBuilderExtensionsTests
{
    [Fact]
    public void AddFoundryResponses_OptionsObject_UsesAgentServerDefaultsOverHostSettings()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();
        builder.Configuration[$"ResponsesServer:{nameof(FoundryResponsesOptions.ResilientBackground)}"] = "true";

        // Act
        builder.AddFoundryResponses(new FoundryResponsesOptions
        {
            AllowStoredOutputEnabled = true,
        });
        using ServiceProvider provider = builder.Services.BuildServiceProvider();
        FoundryResponsesOptions registeredOptions =
            provider.GetRequiredService<IOptions<FoundryResponsesOptions>>().Value;

        // Assert
        Assert.True(registeredOptions.AllowStoredOutputEnabled);
        Assert.False(registeredOptions.ResilientBackground);
    }

    [Fact]
    public void AddFoundryResponses_OptionsObject_ExplicitFalseOverridesHostSettings()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();
        builder.Configuration[$"ResponsesServer:{nameof(FoundryResponsesOptions.ResilientBackground)}"] = "true";

        // Act
        builder.AddFoundryResponses(new FoundryResponsesOptions
        {
            ResilientBackground = false,
        });
        using ServiceProvider provider = builder.Services.BuildServiceProvider();

        // Assert
        Assert.False(
            provider.GetRequiredService<IOptions<FoundryResponsesOptions>>()
                .Value.ResilientBackground);
    }
}

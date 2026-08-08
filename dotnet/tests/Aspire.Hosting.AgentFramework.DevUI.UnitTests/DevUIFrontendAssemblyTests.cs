// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Reflection;

namespace Aspire.Hosting.AgentFramework.DevUI.UnitTests;

/// <summary>
/// Regression tests guarding the fix for
/// https://github.com/microsoft/agent-framework/issues/5779.
///
/// Aspire.Hosting.AgentFramework.DevUI references Microsoft.Agents.AI.DevUI so that
/// the embedded DevUI frontend assets ship with the Aspire integration package. These
/// tests verify that the assembly is loadable at runtime via Assembly.Load and exposes
/// the embedded frontend resources the aggregator depends on.
/// </summary>
public class DevUIFrontendAssemblyTests
{
    /// <summary>
    /// Verifies that the Microsoft.Agents.AI.DevUI assembly is reachable via
    /// <see cref="Assembly.Load(string)"/>, which is how
    /// <c>DevUIAggregatorHostedService.LoadFrontendResources</c> discovers it.
    /// </summary>
    [Fact]
    public void MicrosoftAgentsAIDevUIAssembly_IsLoadableAtRuntime()
    {
        // Act
        var assembly = Assembly.Load("Microsoft.Agents.AI.DevUI");

        // Assert
        Assert.NotNull(assembly);
        Assert.Equal("Microsoft.Agents.AI.DevUI", assembly.GetName().Name);
    }

    /// <summary>
    /// Verifies that the Microsoft.Agents.AI.DevUI assembly exposes at least one
    /// embedded frontend resource using the prefix the aggregator looks for.
    /// </summary>
    [Fact]
    public void MicrosoftAgentsAIDevUIAssembly_ExposesEmbeddedFrontendResources()
    {
        // Arrange
        var assembly = Assembly.Load("Microsoft.Agents.AI.DevUI");
        var prefix = $"{assembly.GetName().Name}.resources.";

        // Act
        var resourceNames = assembly.GetManifestResourceNames();
        var frontendResources = resourceNames
            .Where(n => n.StartsWith(prefix, StringComparison.Ordinal))
            .ToArray();

        // Assert
        Assert.NotEmpty(frontendResources);
    }
}

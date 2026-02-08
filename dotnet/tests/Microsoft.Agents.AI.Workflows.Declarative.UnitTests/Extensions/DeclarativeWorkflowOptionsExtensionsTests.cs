// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.PowerFx;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class DeclarativeWorkflowOptionsExtensionsTests
{
    [Fact]
    public void NullContext_UsesDefaultMaximumExpressionLength()
    {
        // Arrange
        DeclarativeWorkflowOptions? options = null;

        // Act
        RecalcEngine engine = options.CreateRecalcEngine();

        // Assert
        Assert.NotNull(engine);
        Assert.Equal(10000, engine.Config.MaximumExpressionLength);
    }

    [Fact]
    public void OptionsWithoutLimits_UsesDefaults()
    {
        // Arrange
        DeclarativeWorkflowOptions options = CreateOptions();

        // Act
        RecalcEngine engine = options.CreateRecalcEngine();

        // Assert
        Assert.NotNull(engine);
        Assert.Equal(10000, engine.Config.MaximumExpressionLength);
        Assert.True(engine.Config.MaxCallDepth >= 0);
    }

    [Fact]
    public void OptionsWithBothLimits()
    {
        // Arrange
        const int ExpectedLength = 5000;
        const int ExpectedDepth = 12;
        DeclarativeWorkflowOptions context = CreateOptions(ExpectedLength, ExpectedDepth);

        // Act
        RecalcEngine engine = context.CreateRecalcEngine();

        // Assert
        Assert.Equal(ExpectedLength, engine.Config.MaximumExpressionLength);
        Assert.Equal(ExpectedDepth, engine.Config.MaxCallDepth);
    }

    // Factory for creating options and mock provider
    private static DeclarativeWorkflowOptions CreateOptions(
        int? maximumExpressionLength = null,
        int? maximumCallDepth = null)
    {
        Mock<WorkflowAgentProvider> providerMock = new(MockBehavior.Strict);
        return
            new(providerMock.Object)
            {
                MaximumExpressionLength = maximumExpressionLength,
                MaximumCallDepth = maximumCallDepth
            };
    }
}

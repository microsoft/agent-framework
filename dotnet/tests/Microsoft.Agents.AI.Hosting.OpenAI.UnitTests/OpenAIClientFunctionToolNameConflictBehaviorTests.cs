// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for <see cref="OpenAIClientFunctionToolNameConflictBehavior"/>.
/// </summary>
public sealed class OpenAIClientFunctionToolNameConflictBehaviorTests
{
    [Fact]
    public void Reject_ReturnsRejectBehavior()
    {
        // Act
#pragma warning disable MAAI001
        OpenAIClientFunctionToolNameConflictBehavior behavior =
            OpenAIClientFunctionToolNameConflictBehavior.Reject();
#pragma warning restore MAAI001

        // Assert
        Assert.Equal(OpenAIClientFunctionToolNameConflictBehavior.BehaviorKind.Reject, behavior.Kind);
    }

    [Fact]
    public void Ignore_ReturnsIgnoreBehavior()
    {
        // Act
#pragma warning disable MAAI001
        OpenAIClientFunctionToolNameConflictBehavior behavior =
            OpenAIClientFunctionToolNameConflictBehavior.Ignore();
#pragma warning restore MAAI001

        // Assert
        Assert.Equal(OpenAIClientFunctionToolNameConflictBehavior.BehaviorKind.Ignore, behavior.Kind);
    }

    [Fact]
    public void AllowOverride_ReturnsAllowOverrideBehavior()
    {
        // Act
#pragma warning disable MAAI001
        OpenAIClientFunctionToolNameConflictBehavior behavior =
            OpenAIClientFunctionToolNameConflictBehavior.AllowOverride();
#pragma warning restore MAAI001

        // Assert
        Assert.Equal(OpenAIClientFunctionToolNameConflictBehavior.BehaviorKind.AllowOverride, behavior.Kind);
    }
}

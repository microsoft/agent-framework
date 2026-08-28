// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for <see cref="OpenAIClientFunctionToolsOptions"/>.
/// </summary>
public sealed class OpenAIClientFunctionToolsOptionsTests
{
    [Fact]
    public void Constructor_NullConflictBehavior_ThrowsArgumentNullException()
    {
        // Act & Assert
#pragma warning disable MAAI001
        Assert.Throws<ArgumentNullException>(() =>
            new OpenAIClientFunctionToolsOptions(nameConflictBehavior: null!));
#pragma warning restore MAAI001
    }
}

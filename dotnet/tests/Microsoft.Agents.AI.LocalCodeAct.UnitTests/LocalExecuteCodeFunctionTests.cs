// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Xunit;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

/// <summary>
/// Basic tests for LocalExecuteCodeFunction.
/// </summary>
public sealed class LocalExecuteCodeFunctionTests
{
    [Fact]
    public void Constructor_WithValidPath_Succeeds()
    {
        // Arrange & Act
        var function = new LocalExecuteCodeFunction("/usr/bin/python3");

        // Assert
        Assert.NotNull(function);
        Assert.Equal("execute_code", function.Metadata.Name);
        Assert.NotNull(function.Metadata.Description);
    }

    [Fact]
    public void Constructor_WithNullPath_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new LocalExecuteCodeFunction(null!));
    }

    [Fact]
    public void Metadata_HasRequiredCodeParameter()
    {
        // Arrange
        var function = new LocalExecuteCodeFunction("/usr/bin/python3");

        // Act
        var parameters = function.Metadata.Parameters;

        // Assert
        Assert.NotNull(parameters);
        Assert.Single(parameters);
        Assert.Equal("code", parameters[0].Name);
        Assert.True(parameters[0].IsRequired);
    }

    [Fact]
    public void Dispose_CanBeCalledMultipleTimes()
    {
        // Arrange
        var function = new LocalExecuteCodeFunction("/usr/bin/python3");

        // Act & Assert
        function.Dispose();
        function.Dispose(); // Should not throw
    }
}

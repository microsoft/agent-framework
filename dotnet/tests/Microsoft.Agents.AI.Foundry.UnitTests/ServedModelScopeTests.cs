// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Unit tests for <see cref="ServedModelScope"/>: the AsyncLocal carrier that bridges the
/// served-model value from the SCM pipeline policy up to the delegating chat client.
/// </summary>
public sealed class ServedModelScopeTests
{
    [Fact]
    public void Current_DefaultIsNull()
    {
        Assert.Null(ServedModelScope.Current);
    }

    [Fact]
    public void Current_SetAndGet_ReturnsBox()
    {
        // Arrange
        var previous = ServedModelScope.Current;

        try
        {
            // Act
            var box = new StrongBox<string?>("gpt-5-nano-2025-08-07");
            ServedModelScope.Current = box;

            // Assert
            Assert.Same(box, ServedModelScope.Current);
            Assert.Equal("gpt-5-nano-2025-08-07", ServedModelScope.Current!.Value);
        }
        finally
        {
            ServedModelScope.Current = previous;
        }
    }
}

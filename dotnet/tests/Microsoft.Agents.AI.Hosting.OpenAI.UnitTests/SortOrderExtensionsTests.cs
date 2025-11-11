// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Unit tests for SortOrderExtensions.
/// </summary>
public sealed class SortOrderExtensionsTests
{
    [Fact]
    public void ToOrderString_Ascending_ReturnsAsc()
    {
        // Arrange
        const SortOrder Order = SortOrder.Ascending;

        // Act
        string result = Order.ToOrderString();

        // Assert
        Assert.Equal("asc", result);
    }

    [Fact]
    public void ToOrderString_Descending_ReturnsDesc()
    {
        // Arrange
        const SortOrder Order = SortOrder.Descending;

        // Act
        string result = Order.ToOrderString();

        // Assert
        Assert.Equal("desc", result);
    }

    [Fact]
    public void IsAscending_Ascending_ReturnsTrue()
    {
        // Arrange
        const SortOrder Order = SortOrder.Ascending;

        // Act
        bool result = Order.IsAscending();

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void IsAscending_Descending_ReturnsFalse()
    {
        // Arrange
        const SortOrder Order = SortOrder.Descending;

        // Act
        bool result = Order.IsAscending();

        // Assert
        Assert.False(result);
    }
}

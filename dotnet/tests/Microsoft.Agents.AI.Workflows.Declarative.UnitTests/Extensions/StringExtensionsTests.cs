// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class StringExtensionsTests
{
    [Fact]
    public void TrimJsonWithDelimiter()
    {
        // Arrange
        const string Input =
            """
            ```json
            {
                "key": "value"
            }
            ```
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }
    [Fact]
    public void TrimJsonWithPadding()
    {
        // Arrange
        const string Input =
            """
                 
            ```json
            {
                "key": "value"
            }
            ```       
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithUnqualifiedDelimiter()
    {
        // Arrange
        const string Input =
            """
            ```
            {
                "key": "value"
            }
            ```
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithoutDelimiter()
    {
        // Arrange
        const string Input =
            """
            {
                "key": "value"
            }
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimJsonWithoutDelimiterWithPadding()
    {
        // Arrange
        const string Input =
            """

            {
                "key": "value"
            }    
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(
            """
            {
                "key": "value"
            }
            """,
            result);
    }

    [Fact]
    public void TrimMissingWithDelimiter()
    {
        // Arrange
        const string Input =
            """
            ```json
            ```
            """;

        // Act
        string result = Input.TrimJsonDelimiter();

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void TrimEmptyString()
    {
        // Act
        string result = string.Empty.TrimJsonDelimiter();

        // Assert
        Assert.Equal(string.Empty, result);
    }
}

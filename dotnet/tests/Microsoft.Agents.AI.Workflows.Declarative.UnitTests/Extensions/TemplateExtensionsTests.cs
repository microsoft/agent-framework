// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class TemplateExtensionsTests
{
    [Fact]
    public void FormatTemplateWithTextSegments()
    {
        // Arrange
        RecalcEngine engine = new();
        IEnumerable<TemplateLine> template =
        [
            new TemplateLine.Builder
            {
                Segments =
                {
                    new TextSegment.Builder { Value = "Hello " },
                    new TextSegment.Builder { Value = "World" }
                }
            }.Build()
        ];

        // Act
        string result = engine.Format(template);

        // Assert
        Assert.Equal("Hello World", result);
    }

    [Fact]
    public void FormatTemplateWithMultipleLines()
    {
        // Arrange
        RecalcEngine engine = new();
        IEnumerable<TemplateLine> template =
        [
            new TemplateLine.Builder
            {
                Segments =
                {
                    new TextSegment.Builder { Value = "Line 1" }
                }
            }.Build(),
            new TemplateLine.Builder
            {
                Segments =
                {
                    new TextSegment.Builder { Value = "Line 2" }
                }
            }.Build()
        ];

        // Act
        string result = engine.Format(template);

        // Assert
        Assert.Equal("Line 1Line 2", result);
    }

    [Fact]
    public void FormatSingleTemplateLineWithNullValue()
    {
        // Arrange
        RecalcEngine engine = new();
        TemplateLine? line = null;

        // Act
        string result = engine.Format(line);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatSingleTemplateLineWithTextSegment()
    {
        // Arrange
        RecalcEngine engine = new();
        TemplateLine line = new TemplateLine.Builder
        {
            Segments =
            {
                new TextSegment.Builder { Value = "Test" }
            }
        }.Build();

        // Act
        string result = engine.Format(line);

        // Assert
        Assert.Equal("Test", result);
    }

    [Fact]
    public void FormatTextSegmentWithNullValue()
    {
        // Arrange
        RecalcEngine engine = new();
        TextSegment segment = new TextSegment.Builder { Value = null }.Build();

        // Act
        string result = engine.Format(segment);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatTextSegmentWithEmptyValue()
    {
        // Arrange
        RecalcEngine engine = new();
        TextSegment segment = new TextSegment.Builder { Value = "" }.Build();

        // Act
        string result = engine.Format(segment);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatTextSegmentWithValue()
    {
        // Arrange
        RecalcEngine engine = new();
        TextSegment segment = new TextSegment.Builder { Value = "Hello World" }.Build();

        // Act
        string result = engine.Format(segment);

        // Assert
        Assert.Equal("Hello World", result);
    }
}

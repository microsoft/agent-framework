// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

public class TemplateExtensionsTests(ITestOutputHelper output) : RecalcEngineTest(output)
{
    [Fact]
    public void FormatTemplateLines()
    {
        // Arrange
        List<TemplateLine> template =
        [
            TemplateLine.Parse("Hello"),
            TemplateLine.Parse(" "),
            TemplateLine.Parse("World"),
        ];

        // Act
        string? result = this.Engine.Format(template);

        // Assert
        Assert.Equal("Hello World", result);
    }

    [Fact]
    public void FormatTemplateLinesEmpty()
    {
        // Arrange
        List<TemplateLine> template = [];

        // Act
        string? result = this.Engine.Format(template);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatTemplateLine()
    {
        // Arrange
        TemplateLine line = TemplateLine.Parse("Test");

        // Act
        string? result = this.Engine.Format(line);

        // Assert
        Assert.Equal("Test", result);
    }

    [Fact]
    public void FormatTemplateLineNull()
    {
        // Arrange
        TemplateLine? line = null;

        // Act
        string? result = this.Engine.Format(line);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatTextSegment()
    {
        // Arrange
        TemplateSegment textSegment = TemplateSegment.FromText("Hello World");
        TemplateLine line = new([textSegment]);

        // Act
        string? result = this.Engine.Format(line);

        // Assert
        Assert.Equal("Hello World", result);
    }

    [Fact]
    public void FormatExpressionSegment()
    {
        // Arrange
        ExpressionSegment expressionSegment = new(ValueExpression.Expression("1 + 1"));
        TemplateLine line = new([expressionSegment]);

        // Act
        string? result = this.Engine.Format(line);

        // Assert
        Assert.Equal("2", result);
    }

    [Fact]
    public void FormatVariableSegment()
    {
        // Arrange
        this.State.Set("Source", FormulaValue.New("Hello World"));
        this.State.Bind();

        ExpressionSegment expressionSegment = new(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));
        TemplateLine line = new([expressionSegment]);

        // Act
        string? result = this.Engine.Format(line);

        // Assert
        Assert.Equal("Hello World", result);
    }

    [Fact]
    public void FormatExpressionSegmentUndefined()
    {
        // Arrange
        ExpressionSegment expressionSegment = new();
        TemplateLine line = new([expressionSegment]);

        // Act & Assert
        Assert.Throws<DeclarativeModelException>(() => this.Engine.Format(line));
    }

    [Fact]
    public void FormatMultipleSegments()
    {
        // Arrange
        TemplateSegment textSegment = TemplateSegment.FromText("Hello ");
        ExpressionSegment expressionSegment = new(ValueExpression.Expression(@"""World"""));
        TemplateLine line = new([textSegment, expressionSegment]);

        // Act
        string? result = this.Engine.Format(line);

        // Assert
        Assert.Equal("Hello World", result);
    }
}

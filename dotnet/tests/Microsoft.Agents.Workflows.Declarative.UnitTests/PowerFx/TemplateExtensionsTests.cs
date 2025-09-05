// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;
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
        RecalcEngine engine = this.CreateEngine();

        // Act
        string? result = engine.Format(template);

        // Assert
        Assert.Equal("Hello World", result);
    }

    [Fact]
    public void FormatTemplateLinesEmpty()
    {
        // Arrange
        List<TemplateLine> template = [];
        RecalcEngine engine = this.CreateEngine();

        // Act
        string? result = engine.Format(template);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatTemplateLine()
    {
        // Arrange
        TemplateLine line = TemplateLine.Parse("Test");
        RecalcEngine engine = this.CreateEngine();

        // Act
        string? result = engine.Format(line);

        // Assert
        Assert.Equal("Test", result);
    }

    [Fact]
    public void FormatTemplateLineNull()
    {
        // Arrange
        TemplateLine? line = null;
        RecalcEngine engine = this.CreateEngine();

        // Act
        string? result = engine.Format(line);

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatTextSegment()
    {
        // Arrange
        TemplateSegment textSegment = TextSegment.FromText("Hello World");
        TemplateLine line = new([textSegment]);
        RecalcEngine engine = this.CreateEngine();

        // Act
        string? result = engine.Format(line);

        // Assert
        Assert.Equal("Hello World", result);
    }

    [Fact]
    public void FormatExpressionSegment()
    {
        // Arrange
        ExpressionSegment expressionSegment = new(ValueExpression.Expression("1 + 1"));
        TemplateLine line = new([expressionSegment]);
        RecalcEngine engine = this.CreateEngine();

        // Act
        string? result = engine.Format(line);

        // Assert
        Assert.Equal("2", result);
    }

    [Fact]
    public void FormatVariableSegment()
    {
        // Arrange
        this.Scopes.Set("Source", FormulaValue.New("Hello World"));
        ExpressionSegment expressionSegment = new(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));
        TemplateLine line = new([expressionSegment]);
        RecalcEngine engine = this.CreateEngine();
        this.Scopes.Bind(engine);

        // Act
        string? result = engine.Format(line);

        // Assert
        Assert.Equal("Hello World", result);
    }

    [Fact]
    public void FormatExpressionSegmentUndefined()
    {
        // Arrange
        ExpressionSegment expressionSegment = new();
        TemplateLine line = new([expressionSegment]);
        RecalcEngine engine = this.CreateEngine();

        // Act & Assert
        Assert.Throws<DeclarativeModelException>(() => engine.Format(line));
    }

    [Fact]
    public void FormatMultipleSegments()
    {
        // Arrange
        TemplateSegment textSegment = TextSegment.FromText("Hello ");
        ExpressionSegment expressionSegment = new(ValueExpression.Expression(@"""World"""));
        TemplateLine line = new([textSegment, expressionSegment]);
        RecalcEngine engine = this.CreateEngine();

        // Act
        string? result = engine.Format(line);

        // Assert
        Assert.Equal("Hello World", result);
    }
}

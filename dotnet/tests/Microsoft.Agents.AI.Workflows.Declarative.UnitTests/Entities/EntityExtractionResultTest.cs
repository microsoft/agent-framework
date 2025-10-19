// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Entities;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Entities;

/// <summary>
/// Tests for <see cref="EntityExtractionResult"/>.
/// </summary>
public sealed class EntityExtractionResultTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Fact]
    public void ConstructorWithErrorMessage()
    {
        // Arrange
        const string ErrorMessage = "Test error message";

        // Act
        EntityExtractionResult result = new(ErrorMessage);

        // Assert
        Assert.Null(result.Value);
        Assert.Equal(ErrorMessage, result.ErrorMessage);
        Assert.False(result.IsValid);
    }

    [Fact]
    public void ConstructorWithNullValue()
    {
        // Arrange
        FormulaValue? value = null;

        // Act
        EntityExtractionResult result = new(value);

        // Assert
        Assert.Null(result.Value);
        Assert.Null(result.ErrorMessage);
        Assert.False(result.IsValid);
    }

    [Fact]
    public void ConstructorWithNumberValue()
    {
        // Arrange
        FormulaValue value = FormulaValue.New(double.MaxValue);

        // Act
        EntityExtractionResult result = new(value);

        // Assert
        NumberValue numberValue = Assert.IsType<NumberValue>(result.Value);
        Assert.Equal(double.MaxValue, numberValue.Value);
    }

    [Fact]
    public void ConstructorWithBlankValue_IsValid()
    {
        // Arrange
        FormulaValue value = FormulaValue.NewBlank();

        // Act
        EntityExtractionResult result = new(value);

        // Assert
        Assert.Equal(value, result.Value);
        Assert.True(result.IsValid);
    }
}

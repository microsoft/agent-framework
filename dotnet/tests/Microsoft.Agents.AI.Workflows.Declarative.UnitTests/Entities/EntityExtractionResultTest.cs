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
    public void ConstructorWithValue_InitializesCorrectly()
    {
        // Arrange
        FormulaValue value = FormulaValue.New(42);

        // Act
        EntityExtractionResult result = new(value);

        // Assert
        Assert.Equal(value, result.Value);
        Assert.Null(result.ErrorMessage);
        Assert.True(result.IsValid);
    }

    [Fact]
    public void ConstructorWithErrorMessage_InitializesCorrectly()
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
    public void ConstructorWithNullValue_IsValid()
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
    public void IsValid_ReturnsTrueWhenValueIsNotNull()
    {
        // Arrange
        FormulaValue value = FormulaValue.New("test");

        // Act
        EntityExtractionResult result = new(value);

        // Assert
        Assert.True(result.IsValid);
    }

    [Fact]
    public void IsValid_ReturnsFalseWhenValueIsNull()
    {
        // Arrange
        const string ErrorMessage = "Error occurred";

        // Act
        EntityExtractionResult result = new(ErrorMessage);

        // Assert
        Assert.False(result.IsValid);
    }

    [Theory]
    [InlineData(123)]
    [InlineData(456.78)]
    public void ConstructorWithNumberValue_PreservesValue(double number)
    {
        // Arrange
        FormulaValue value = FormulaValue.New(number);

        // Act
        EntityExtractionResult result = new(value);

        // Assert
        Assert.Equal(value, result.Value);
        Assert.True(result.IsValid);
    }

    [Theory]
    [InlineData("Error 1")]
    [InlineData("Error 2")]
    [InlineData("Invalid input")]
    public void ConstructorWithErrorMessage_PreservesMessage(string errorMessage)
    {
        // Act
        EntityExtractionResult result = new(errorMessage);

        // Assert
        Assert.Equal(errorMessage, result.ErrorMessage);
        Assert.False(result.IsValid);
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

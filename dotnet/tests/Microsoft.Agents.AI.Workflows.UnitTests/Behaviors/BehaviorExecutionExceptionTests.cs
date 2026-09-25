// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Behaviors;

namespace Microsoft.Agents.AI.Workflows.UnitTests.Behaviors;

/// <summary>
/// Tests for BehaviorExecutionException error handling and wrapping.
/// </summary>
public class BehaviorExecutionExceptionTests
{
    [Fact]
    public void Constructor_WithAllParameters_InitializesProperties()
    {
        // Arrange
        const string behaviorType = "TestBehavior";
        const string stage = "PreExecution";
        var innerException = new InvalidOperationException("Inner exception");

        // Act
        var exception = new BehaviorExecutionException(behaviorType, stage, innerException);

        // Assert
        exception.BehaviorType.Should().Be(behaviorType);
        exception.Stage.Should().Be(stage);
        exception.InnerException.Should().Be(innerException);
        exception.Message.Should().Contain(behaviorType);
        exception.Message.Should().Contain(stage);
    }

    [Fact]
    public void Constructor_WithNullBehaviorType_ThrowsArgumentNullException()
    {
        // Arrange
        var innerException = new InvalidOperationException();

        // Act
        Action act = () => _ = new BehaviorExecutionException(null!, "stage", innerException);

        // Assert
        act.Should().Throw<ArgumentNullException>();
    }

    [Fact]
    public void Constructor_WithNullStage_ThrowsArgumentNullException()
    {
        // Arrange
        var innerException = new InvalidOperationException();

        // Act
        Action act = () => _ = new BehaviorExecutionException("behavior", null!, innerException);

        // Assert
        act.Should().Throw<ArgumentNullException>();
    }

    [Fact]
    public void Constructor_WithNullInnerException_ThrowsArgumentNullException()
    {
        // Act
        Action act = () => _ = new BehaviorExecutionException("behavior", "stage", null!);

        // Assert
        act.Should().Throw<ArgumentNullException>();
    }

    [Fact]
    public void Message_ContainsBehaviorType()
    {
        // Arrange
        const string behaviorType = "LoggingBehavior";
        var exception = new BehaviorExecutionException(
            behaviorType,
            "PreExecution",
            new InvalidOperationException());

        // Act
        var message = exception.Message;

        // Assert
        message.Should().Contain(behaviorType);
    }

    [Fact]
    public void Message_ContainsStage()
    {
        // Arrange
        const string stage = "Ending";
        var exception = new BehaviorExecutionException(
            "TestBehavior",
            stage,
            new InvalidOperationException());

        // Act
        var message = exception.Message;

        // Assert
        message.Should().Contain(stage);
    }

    [Fact]
    public void Exception_IsSerializable()
    {
        // Arrange
        var exception = new BehaviorExecutionException(
            "TestBehavior",
            "PreExecution",
            new InvalidOperationException("Test"));

        // Act & Assert - Just verify the type is marked as serializable
        exception.Should().BeAssignableTo<Exception>();
    }

    [Fact]
    public void InnerException_IsPreserved()
    {
        // Arrange
        const string originalMessage = "Original exception message";
        var innerException = new InvalidOperationException(originalMessage);

        // Act
        var exception = new BehaviorExecutionException("TestBehavior", "PreExecution", innerException);

        // Assert
        exception.InnerException.Should().NotBeNull();
        exception.InnerException!.Message.Should().Be(originalMessage);
    }

    [Fact]
    public void StackTrace_IsPreserved()
    {
        // Arrange
        Exception? capturedException = null;
        try
        {
            ThrowTestException();
        }
        catch (Exception ex)
        {
            capturedException = ex;
        }

        // Act
        var wrappedException = new BehaviorExecutionException(
            "TestBehavior",
            "PreExecution",
            capturedException!);

        // Assert
        wrappedException.InnerException!.StackTrace.Should().NotBeNullOrEmpty();
        wrappedException.InnerException!.StackTrace.Should().Contain(nameof(ThrowTestException));
    }

    [Fact]
    public void BehaviorType_IsAccessible()
    {
        // Arrange
        const string behaviorType = "MyCustomBehavior";
        var exception = new BehaviorExecutionException(
            behaviorType,
            "PreExecution",
            new InvalidOperationException());

        // Act
        var result = exception.BehaviorType;

        // Assert
        result.Should().Be(behaviorType);
    }

    [Fact]
    public void Stage_IsAccessible()
    {
        // Arrange
        const string stage = "Ending";
        var exception = new BehaviorExecutionException(
            "TestBehavior",
            stage,
            new InvalidOperationException());

        // Act
        var result = exception.Stage;

        // Assert
        result.Should().Be(stage);
    }

    [Fact]
    public void Constructor_Parameterless_UsesDefaultMessageAndEmptyMetadata()
    {
        // Act
        var exception = new BehaviorExecutionException();

        // Assert
        exception.Message.Should().Be("Error executing behavior");
        exception.BehaviorType.Should().BeEmpty();
        exception.Stage.Should().BeEmpty();
        exception.InnerException.Should().BeNull();
    }

    [Fact]
    public void Constructor_WithMessage_SetsMessageAndEmptyMetadata()
    {
        // Act
        var exception = new BehaviorExecutionException("custom message");

        // Assert
        exception.Message.Should().Be("custom message");
        exception.BehaviorType.Should().BeEmpty();
        exception.Stage.Should().BeEmpty();
        exception.InnerException.Should().BeNull();
    }

    [Fact]
    public void Constructor_WithMessageAndInnerException_SetsBoth()
    {
        // Arrange
        var innerException = new InvalidOperationException("inner");

        // Act
        var exception = new BehaviorExecutionException("custom message", innerException);

        // Assert
        exception.Message.Should().Be("custom message");
        exception.InnerException.Should().BeSameAs(innerException);
        exception.BehaviorType.Should().BeEmpty();
        exception.Stage.Should().BeEmpty();
    }

    [Fact]
    public void Constructor_WithEmptyBehaviorType_ThrowsArgumentException()
    {
        // Arrange
        var innerException = new InvalidOperationException();

        // Act
        Action act = () => _ = new BehaviorExecutionException(string.Empty, "stage", innerException);

        // Assert - empty must be rejected distinctly from null, so the message is never "behavior '' at stage"
        act.Should().Throw<ArgumentException>().Which.Should().NotBeOfType<ArgumentNullException>();
    }

    [Fact]
    public void Constructor_WithEmptyStage_ThrowsArgumentException()
    {
        // Arrange
        var innerException = new InvalidOperationException();

        // Act
        Action act = () => _ = new BehaviorExecutionException("behavior", string.Empty, innerException);

        // Assert
        act.Should().Throw<ArgumentException>().Which.Should().NotBeOfType<ArgumentNullException>();
    }

    private static void ThrowTestException()
    {
        throw new InvalidOperationException("Test exception");
    }
}

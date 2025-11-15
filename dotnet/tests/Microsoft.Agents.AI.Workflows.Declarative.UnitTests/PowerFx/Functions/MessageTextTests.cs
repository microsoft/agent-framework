// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx.Functions;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.PowerFx.Functions;

public sealed class MessageTextTests
{
    [Fact]
    public void Construct_Function()
    {
        MessageText.StringInput function1 = new();
        Assert.NotNull(function1);

        MessageText.RecordInput function2 = new();
        Assert.NotNull(function2);

        MessageText.TableInput function3 = new();
        Assert.NotNull(function3);
    }

    [Fact]
    public void Execute_ReturnsEmpty_ForEmptyInput()
    {
        // Arrange
        StringValue sourceValue = FormulaValue.New(string.Empty);

        // Act
        FormulaValue result = MessageText.StringInput.Execute(sourceValue);

        // Assert
        StringValue stringResult = Assert.IsType<StringValue>(result);
        Assert.Empty(stringResult.Value);
    }

    [Fact]
    public void Execute_ReturnsText_ForStringInput()
    {
        // Arrange
        StringValue sourceValue = FormulaValue.New("wowsie");

        // Act
        FormulaValue result = MessageText.StringInput.Execute(sourceValue);

        // Assert
        StringValue stringResult = Assert.IsType<StringValue>(result);
        Assert.Equal(sourceValue.Value, stringResult.Value);
    }

    [Fact]
    public void Execute_ReturnsText_ForMessageInput()
    {
        // Arrange
        RecordValue sourceValue = new ChatMessage(ChatRole.User, "test message").ToRecord();

        // Act
        FormulaValue result = MessageText.RecordInput.Execute(sourceValue);

        // Assert
        StringValue stringResult = Assert.IsType<StringValue>(result);
        Assert.Equal("test message", stringResult.Value);
    }

    [Fact]
    public void Execute_ReturnsEmpty_ForUnknownInput()
    {
        // Arrange
        RecordValue sourceValue = FormulaValue.NewRecordFromFields(new NamedValue("Anything", FormulaValue.New(333)));

        // Act
        FormulaValue result = MessageText.RecordInput.Execute(sourceValue);

        // Assert
        StringValue stringResult = Assert.IsType<StringValue>(result);
        Assert.Empty(stringResult.Value);
    }

    [Fact]
    public void Execute_ReturnsText_ForMessagesInput()
    {
        // Arrange
        TableValue sourceValue = new ChatMessage[]
            {
                new(ChatRole.User, "test message 1"),
                new(ChatRole.User, "test message 2"),
            }.ToTable();

        // Act
        FormulaValue result = MessageText.TableInput.Execute(sourceValue);

        // Assert
        StringValue stringResult = Assert.IsType<StringValue>(result);
        Assert.Equal("test message 1\ntest message 2", stringResult.Value);
    }

    [Fact]
    public void Execute_ReturnsEmpty_ForEmptyList()
    {
        // Arrange
        TableValue sourceValue = Array.Empty<ChatMessage>().ToTable();

        // Act
        FormulaValue result = MessageText.TableInput.Execute(sourceValue);

        // Assert
        StringValue stringResult = Assert.IsType<StringValue>(result);
        Assert.Empty(stringResult.Value);
    }
}

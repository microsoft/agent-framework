// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx.Functions;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.PowerFx.Functions;

public sealed class AgentMessageTests
{
    [Fact]
    public void Construct_Function()
    {
        AgentMessage function = new();
        Assert.NotNull(function);
    }

    [Fact]
    public void Execute_ReturnsBlank_ForEmptyInput()
    {
        // Arrange
        StringValue sourceValue = FormulaValue.New(string.Empty);

        // Act
        FormulaValue result = AgentMessage.Execute(sourceValue);

        // Assert
        Assert.IsType<BlankValue>(result);
    }

    [Fact]
    public void Execute_ReturnsExpectedRecord_ForNonEmptyInput()
    {
        const string Text = "Hello";
        FormulaValue sourceValue = FormulaValue.New(Text);
        StringValue stringValue = Assert.IsType<StringValue>(sourceValue);

        FormulaValue result = AgentMessage.Execute(stringValue);

        RecordValue recordResult = Assert.IsType<RecordValue>(result, exactMatch: false);

        // Discriminator
        FormulaValue discriminator = recordResult.GetField(TypeSchema.Discriminator);
        StringValue discriminatorValue = Assert.IsType<StringValue>(discriminator);
        Assert.Equal(nameof(ChatMessage), discriminatorValue.Value);

        // Role
        FormulaValue role = recordResult.GetField(TypeSchema.Message.Fields.Role);
        StringValue roleValue = Assert.IsType<StringValue>(role);
        Assert.Equal(ChatRole.Assistant.Value, roleValue.Value);

        // Content table
        FormulaValue content = recordResult.GetField(TypeSchema.Message.Fields.Content);
        TableValue table = Assert.IsType<TableValue>(content, exactMatch: false);

        List<RecordValue> rows = table.Rows.Select(value => value.Value).ToList();
        Assert.Single(rows);

        StringValue contentType = Assert.IsType<StringValue>(rows[0].GetField(TypeSchema.Message.Fields.ContentType));
        Assert.Equal(TypeSchema.Message.ContentTypes.Text, contentType.Value);

        StringValue contentValue = Assert.IsType<StringValue>(rows[0].GetField(TypeSchema.Message.Fields.ContentValue));
        Assert.Equal(Text, contentValue.Value);
    }
}

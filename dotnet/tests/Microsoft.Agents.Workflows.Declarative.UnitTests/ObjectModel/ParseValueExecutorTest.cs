// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.ObjectModel;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ParseValueExecutor"/>.
/// </summary>
public sealed class ParseValueExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ParseTable()
    {
        // Arrange
        RecordDataType.Builder recordBuilder =
            new()
            {
                Properties =
                {
                    {"key1", new PropertyInfo.Builder() { Type = DataType.String } },
                }
            };
        ParseValue model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ParseTable)),
                recordBuilder,
                @"{ ""key1"": ""val1"" }");

        // Act
        ParseValueExecutor action = new(model, this.GetState());
        await this.Execute(action);

        // Assert
        this.VerifyModel(model, action);
        this.VerifyState("Target", FormulaValue.NewRecordFromFields(new NamedValue("key1", FormulaValue.New("val1"))));
    }

    [Fact]
    public async Task ParseBoolean()
    {
        // Arrange
        ParseValue model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ParseTable)),
                new BooleanDataType.Builder(),
                "True");

        // Act
        ParseValueExecutor action = new(model, this.GetState());
        await this.Execute(action);

        // Assert
        this.VerifyModel(model, action);
        this.VerifyState("Target", FormulaValue.New(true));
    }

    [Fact]
    public async Task ParseNumber()
    {
        // Arrange
        ParseValue model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ParseNumber)),
                new NumberDataType.Builder(),
                "42");

        // Act
        ParseValueExecutor action = new(model, this.GetState());
        await this.Execute(action);

        // Assert
        this.VerifyModel(model, action);
        this.VerifyState("Target", FormulaValue.New(42));
    }

    [Fact]
    public async Task ParseString()
    {
        // Arrange
        ParseValue model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ParseString)),
                new StringDataType.Builder(),
                "Hello, World!");

        // Act
        ParseValueExecutor action = new(model, this.GetState());
        await this.Execute(action);

        // Assert
        this.VerifyModel(model, action);
        this.VerifyState("Target", FormulaValue.New("Hello, World!"));
    }

    private ParseValue CreateModel(string displayName, DataType.Builder typeBuilder, string sourceText)
    {
        ParseValue.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                ValueType = typeBuilder,
                Variable = PropertyPath.TopicVariable("Target"),
                Value = new ValueExpression.Builder(ValueExpression.Literal(StringDataValue.Create(sourceText))),
            };

        ParseValue model = this.AssignParent<ParseValue>(actionBuilder);

        return model;
    }
}

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
    public async Task ParseTableAsync()
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
                this.FormatDisplayName(nameof(ParseTableAsync)),
                recordBuilder,
                @"{ ""key1"": ""val1"" }");

        // Act
        ParseValueExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState("Target", FormulaValue.NewRecordFromFields(new NamedValue("key1", FormulaValue.New("val1"))));
    }

    [Fact]
    public async Task ParseBooleanAsync()
    {
        // Arrange
        ParseValue model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ParseTableAsync)),
                new BooleanDataType.Builder(),
                "True");

        // Act
        ParseValueExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState("Target", FormulaValue.New(true));
    }

    [Fact]
    public async Task ParseNumberAsync()
    {
        // Arrange
        ParseValue model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ParseNumberAsync)),
                new NumberDataType.Builder(),
                "42");

        // Act
        ParseValueExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState("Target", FormulaValue.New(42));
    }

    [Fact]
    public async Task ParseStringAsync()
    {
        // Arrange
        ParseValue model =
            this.CreateModel(
                this.FormatDisplayName(nameof(ParseStringAsync)),
                new StringDataType.Builder(),
                "Hello, World!");

        // Act
        ParseValueExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
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

        return AssignParent<ParseValue>(actionBuilder);
    }
}

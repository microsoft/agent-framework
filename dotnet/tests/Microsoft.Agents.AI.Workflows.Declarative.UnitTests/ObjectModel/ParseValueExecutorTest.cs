// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="ParseValueExecutor"/>.
/// </summary>
public sealed class ParseValueExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ParseRecordAsync()
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

        // Act & Assert
        await this.ExecuteTestAsync(
            this.FormatDisplayName(nameof(ParseRecordAsync)),
            recordBuilder,
            @"{ ""key1"": ""val1"" }",
            FormulaValue.NewRecordFromFields(new NamedValue("key1", FormulaValue.New("val1"))));
    }

    [Fact]
    public async Task ParseTableAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            this.FormatDisplayName(nameof(ParseTableAsync)),
            DataType.EmptyTable,
            @"[""apple"",""banana"",""cat""]",
            FormulaValue.NewSingleColumnTable(FormulaValue.New("apple"), FormulaValue.New("banana"), FormulaValue.New("cat")));
    }

    [Fact]
    public async Task ParseBooleanAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            this.FormatDisplayName(nameof(ParseBooleanAsync)),
            new BooleanDataType.Builder(),
            "True",
            FormulaValue.New(true));
    }

    [Fact]
    public async Task ParseNumberAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            this.FormatDisplayName(nameof(ParseNumberAsync)),
            new NumberDataType.Builder(),
            "42",
            FormulaValue.New(42));
    }

    [Fact]
    public async Task ParseStringAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            this.FormatDisplayName(nameof(ParseStringAsync)),
            new StringDataType.Builder(),
            "Hello, World!",
            FormulaValue.New("Hello, World!"));
    }

    private async Task ExecuteTestAsync(
        string displayName,
        DataType.Builder dataBuilder,
        string sourceText,
        FormulaValue expectedValue)
    {
        ParseValue model =
            this.CreateModel(
                displayName,
                "Target",
                dataBuilder,
                sourceText);

        // Act
        ParseValueExecutor action = new(model, this.State);
        await this.ExecuteAsync(action);

        // Assert
        VerifyModel(model, action);
        this.VerifyState("Target", expectedValue);
    }

    private ParseValue CreateModel(
        string displayName,
        string variableName,
        DataType.Builder typeBuilder,
        string sourceText)
    {
        ParseValue.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                ValueType = typeBuilder,
                Variable = PropertyPath.TopicVariable(variableName),
                Value = new ValueExpression.Builder(ValueExpression.Literal(StringDataValue.Create(sourceText))),
            };

        return AssignParent<ParseValue>(actionBuilder);
    }
}

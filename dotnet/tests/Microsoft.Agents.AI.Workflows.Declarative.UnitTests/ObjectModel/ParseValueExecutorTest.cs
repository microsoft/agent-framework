// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.PowerFx.Types;

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

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ParseConditionalExpressionContinuesAsync(bool value)
    {
        // Arrange
        this.State.Set("Setting", FormulaValue.New(value), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        ParseValue.Builder builder = this.CreateModel(
            nameof(ParseConditionalExpressionContinuesAsync), "Target", new NumberDataType.Builder(), "").ToBuilder();
        builder.Value = new ValueExpression.Builder(ValueExpression.Expression("If(Env.Setting, \"42\", \"x\")"));
        ParseValueExecutor action = new(builder.Build(), this.State);
        bool continued = false;

        // Act
        await this.ExecuteAsync(action, "next_action", (context, message, cancellationToken) =>
        {
            continued = true;
            return default;
        });

        // Assert
        Assert.True(continued);
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("Target"));
        if (value)
        {
            this.VerifyState("Target", FormulaValue.New(42));
        }
        else
        {
            this.VerifyUndefined("Target");
        }
    }

    [Theory]
    [InlineData("Number", "x", true)]
    [InlineData("Number", "x", false)]
    [InlineData("Number", "79228162514264337593543950336", true)]
    [InlineData("Number", "79228162514264337593543950336", false)]
    [InlineData("Boolean", "x", true)]
    [InlineData("Boolean", "x", false)]
    [InlineData("Record", "x", true)]
    [InlineData("Record", "x", false)]
    [InlineData("Record", "[]", true)]
    [InlineData("Record", "[]", false)]
    [InlineData("Table", "x", true)]
    [InlineData("Table", "x", false)]
    [InlineData("Table", "[[1]]", true)]
    [InlineData("Table", "[[1]]", false)]
    public async Task ParseInvalidValueAsync(string valueType, string sourceText, bool isSensitive)
    {
        // Arrange
        DataType.Builder typeBuilder = valueType switch
        {
            "Number" => new NumberDataType.Builder(),
            "Boolean" => new BooleanDataType.Builder(),
            "Record" => new RecordDataType.Builder(),
            _ => DataType.EmptyTable.ToBuilder(),
        };
        this.State.Set("Source", FormulaValue.New(sourceText),
            sensitivity: isSensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None);
        ParseValue.Builder builder = this.CreateModel(
            nameof(ParseInvalidValueAsync), "Target", typeBuilder, "").ToBuilder();
        builder.Value = new ValueExpression.Builder(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));
        ParseValueExecutor action = new(builder.Build(), this.State);

        // Act & Assert
        if (isSensitive)
        {
            await this.ExecuteAsync(action);
            this.VerifyUndefined("Target");
            Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("Target"));
        }
        else
        {
            await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ParseUnsupportedTargetTypeAsync(bool isSensitive)
    {
        // Arrange
        this.State.Set("Source", FormulaValue.New("x"),
            sensitivity: isSensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None);
        ParseValue.Builder builder = this.CreateModel(
            nameof(ParseUnsupportedTargetTypeAsync), "Target", DataType.Any.ToBuilder(), "").ToBuilder();
        builder.Value = new ValueExpression.Builder(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));
        ParseValueExecutor action = new(builder.Build(), this.State);

        // Act
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));

        // Assert
        Assert.IsType<DeclarativeModelException>(exception.InnerException);
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

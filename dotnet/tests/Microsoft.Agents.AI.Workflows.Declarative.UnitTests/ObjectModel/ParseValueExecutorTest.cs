// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx.Types;
using Shared.UnitTests;

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
    [InlineData("Number", "text")]
    [InlineData("Number", "999999999999999999999999999999999999")]
    [InlineData("Float", "text")]
    [InlineData("Boolean", "text")]
    [InlineData("DateTime", "text")]
    [InlineData("Date", "text")]
    [InlineData("Time", "text")]
    [InlineData("Record", "text")]
    [InlineData("Record", "42")]
    [InlineData("Table", "text")]
    [InlineData("Table", "[[1]]")]
    public async Task ParseInvalidExpressionContinuesAsync(string typeName, string sourceText)
    {
        // Arrange
        DataType.Builder typeBuilder = typeName switch
        {
            "Number" => new NumberDataType.Builder(),
            "Float" => new FloatDataType.Builder(),
            "Boolean" => new BooleanDataType.Builder(),
            "DateTime" => new DateTimeDataType.Builder(),
            "Date" => new DateDataType.Builder(),
            "Time" => new TimeDataType.Builder(),
            "Record" => new RecordDataType.Builder(),
            "Table" => DataType.EmptyTable,
            _ => throw new ArgumentOutOfRangeException(nameof(typeName)),
        };
        this.State.Set("Setting", FormulaValue.New(sourceText), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        ParseValue model = this.CreateModel(
            nameof(ParseInvalidExpressionContinuesAsync),
            "Target",
            typeBuilder,
            ValueExpression.Expression("Env.Setting"));
        using CapturingLoggerFactory loggerFactory = new();
        ParseValueExecutor action = new(model, this.State)
        {
            Logger = loggerFactory.CreateLogger<DeclarativeActionExecutor>(),
        };
        bool continued = false;

        // Act
        await this.ExecuteAsync(action, "next_action", (context, message, cancellationToken) =>
        {
            continued = true;
            return default;
        });

        // Assert
        Assert.True(continued);
        Assert.IsType<BlankValue>(this.State.Get("Target"));
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("Target"));
        (LogLevel level, string warning) = Assert.Single(loggerFactory.Entries);
        Assert.Equal(LogLevel.Warning, level);
        Assert.Contains(action.Id, warning, StringComparison.Ordinal);
        Assert.DoesNotContain(sourceText, warning.Replace(action.Id, string.Empty), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ParseConditionalExpressionContinuesAsync(bool value)
    {
        // Arrange
        this.State.Set("Setting", FormulaValue.New(value), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        ParseValue.Builder builder = this.CreateModel(
            nameof(ParseConditionalExpressionContinuesAsync),
            "Target",
            new NumberDataType.Builder(),
            ValueExpression.Expression("")).ToBuilder();
        builder.Value = new ValueExpression.Builder(ValueExpression.Expression("If(Env.Setting, \"42\", \"x\")"));
        ParseValueExecutor action = new(builder.Build(), this.State);

        // Act
        bool continued = false;
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
            nameof(ParseInvalidValueAsync), "Target", typeBuilder, ValueExpression.Expression("")).ToBuilder();
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
    public async Task ParseUnsupportedTargetTypeFailsAsync(bool isSensitive)
    {
        // Arrange
        this.State.Set("Source", FormulaValue.New("x"),
            sensitivity: isSensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None);
        ParseValue.Builder builder = this.CreateModel(
            nameof(ParseUnsupportedTargetTypeFailsAsync),
            "Target",
            DataType.Any.ToBuilder(),
            ValueExpression.Expression("")).ToBuilder();
        builder.Value = new ValueExpression.Builder(ValueExpression.Variable(PropertyPath.TopicVariable("Source")));
        ParseValueExecutor action = new(builder.Build(), this.State);

        // Act
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));

        // Assert
        Assert.IsType<DeclarativeModelException>(exception.InnerException);
    }

    [Fact]
    public async Task ParseValidExpressionPreservesLabelAsync()
    {
        // Arrange
        this.State.Set("Setting", FormulaValue.New("42"), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        ParseValue model = this.CreateModel(
            nameof(ParseValidExpressionPreservesLabelAsync),
            "Target",
            new NumberDataType.Builder(),
            ValueExpression.Expression("Env.Setting"));
        ParseValueExecutor action = new(model, this.State);

        // Act
        await this.ExecuteAsync(action);

        // Assert
        this.VerifyState("Target", FormulaValue.New(42));
        Assert.Equal(SensitivityLevel.Sensitive, this.State.GetSensitivity("Target"));
    }

    [Fact]
    public async Task ParseInvalidLiteralFailsAsync()
    {
        // Arrange
        ParseValue model = this.CreateModel(
            nameof(ParseInvalidLiteralFailsAsync),
            "Target",
            new NumberDataType.Builder(),
            ValueExpression.Literal(StringDataValue.Create("text")));
        ParseValueExecutor action = new(model, this.State);

        // Act
        DeclarativeActionException exception = await Assert.ThrowsAsync<DeclarativeActionException>(() => this.ExecuteAsync(action));

        // Assert
        Assert.IsType<FormatException>(exception.InnerException);
    }

    [Fact]
    public async Task ParseUnsupportedTypeFailsAsync()
    {
        // Arrange
        this.State.Set("Setting", FormulaValue.New("42"), VariableScopeNames.Environment, SensitivityLevel.Sensitive);
        ParseValue model = this.CreateModel(
            nameof(ParseUnsupportedTypeFailsAsync),
            "Target",
            new ColorDataType.Builder(),
            ValueExpression.Expression("Env.Setting"));
        ParseValueExecutor action = new(model, this.State);

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
                ValueExpression.Literal(StringDataValue.Create(sourceText)));

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
        ValueExpression value)
    {
        ParseValue.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                ValueType = typeBuilder,
                Variable = PropertyPath.TopicVariable(variableName),
                Value = new ValueExpression.Builder(value),
            };

        return AssignParent<ParseValue>(actionBuilder);
    }
}

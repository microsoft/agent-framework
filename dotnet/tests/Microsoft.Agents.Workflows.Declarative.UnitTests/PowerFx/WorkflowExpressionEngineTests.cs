// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Immutable;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Exceptions;
using Microsoft.PowerFx.Types;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

public class WorkflowExpressionEngineTests : RecalcEngineTest
{
    private static class Variables
    {
        public const string GlobalValue = nameof(GlobalValue);
        public const string BoolValue = nameof(BoolValue);
        public const string StringValue = nameof(StringValue);
        public const string IntValue = nameof(IntValue);
        public const string NumberValue = nameof(NumberValue);
        public const string EnumValue = nameof(EnumValue);
        public const string ObjectValue = nameof(ObjectValue);
        public const string ArrayValue = nameof(ArrayValue);
        public const string BlankValue = nameof(BlankValue);
    }

    public static readonly RecordValue ObjectData = FormulaValue.NewRecordFromFields(new NamedValue(nameof(EnvironmentVariableReference.SchemaName), FormulaValue.New("test")));
    public static readonly TableValue TableData = FormulaValue.NewSingleColumnTable(FormulaValue.New("a"), FormulaValue.New("b"));

    public WorkflowExpressionEngineTests(ITestOutputHelper output)
        : base(output)
    {
        this.State.Set(Variables.GlobalValue, FormulaValue.New(255), VariableScopeNames.Global);
        this.State.Set(Variables.BoolValue, FormulaValue.New(true), VariableScopeNames.Topic);
        this.State.Set(Variables.StringValue, FormulaValue.New("Hello World"), VariableScopeNames.Topic);
        this.State.Set(Variables.IntValue, FormulaValue.New(long.MaxValue), VariableScopeNames.Topic);
        this.State.Set(Variables.NumberValue, FormulaValue.New(33.3), VariableScopeNames.Topic);
        this.State.Set(Variables.EnumValue, FormulaValue.New(nameof(VariablesToClear.ConversationScopedVariables)), VariableScopeNames.Topic);
        this.State.Set(Variables.ObjectValue, ObjectData, VariableScopeNames.Topic);
        this.State.Set(Variables.ArrayValue, TableData, VariableScopeNames.Topic);
        this.State.Set(Variables.BlankValue, FormulaValue.NewBlank(), VariableScopeNames.Topic);
        this.State.Bind();
    }

    #region BoolExpression Tests

    [Fact]
    public void BoolExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((BoolExpression)null!);

    [Fact]
    public void BoolExpressionGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(BoolExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)));

    [Fact]
    public void BoolExpressionGetValueForLiteral() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Literal(true),
            expectedValue: true);

    [Fact]
    public void BoolExpressionGetValueForBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: false);

    [Fact]
    public void BoolExpressionGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Variable(PropertyPath.TopicVariable(Variables.BoolValue)),
            expectedValue: true);
    }

    [Fact]
    public void BoolExpressionGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Expression("true || false"),
            expectedValue: true);

    #endregion

    #region StringExpression Tests

    [Fact]
    public void StringExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((StringExpression)null!);

    [Fact]
    public void StringExpressionGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(StringExpression.Variable(PropertyPath.TopicVariable(Variables.BoolValue)));

    [Fact]
    public void StringExpressionGetValueForStringExpressionBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: string.Empty);

    [Fact]
    public void StringExpressionGetValueForLiteral() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Literal("test"),
            expectedValue: "test");

    [Fact]
    public void StringExpressionGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)),
            expectedValue: "Hello World");
    }

    [Fact]
    public void StringExpressionGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Expression(@"""A"" & ""B"""),
            expectedValue: "AB");

    [Fact]
    public void StringExpressionGetValueForRecord()
    {
        // Arrange
        RecordValue state = FormulaValue.NewRecordFromFields([new NamedValue("test", FormulaValue.New("value"))]);
        this.State.Set("TestRecord", state, VariableScopeNames.Global);
        this.State.Bind();

        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Variable(PropertyPath.Create("Global.TestRecord")),
            expectedValue:
                """
                {
                  "test": "value"
                }
                """.Replace("\n", Environment.NewLine));
    }

    #endregion

    #region IntExpression Tests

    [Fact]
    public void IntExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((IntExpression)null!);

    [Fact]
    public void IntExpressionGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(IntExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)));

    [Fact]
    public void IntExpressionGetValueForIntExpressionBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: 0);

    [Fact]
    public void IntExpressionGetValueForLiteral() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Literal(7),
            expectedValue: 7);

    [Fact]
    public void IntExpressionGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Variable(PropertyPath.TopicVariable(Variables.IntValue)),
            expectedValue: long.MaxValue);
    }

    [Fact]
    public void IntExpressionGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Expression("1 + 6"),
            expectedValue: 7);

    #endregion

    #region NumberExpression Tests

    [Fact]
    public void NumberExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((NumberExpression)null!);

    [Fact]
    public void NumberExpressionGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(NumberExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)));

    [Fact]
    public void NumberExpressionGetValueForBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: 0);

    [Fact]
    public void NumberExpressionGetValueForLiteral() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Literal(3.14),
            expectedValue: 3.14);

    [Fact]
    public void NumberExpressionGetValueForVariable() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Variable(PropertyPath.TopicVariable(Variables.NumberValue)),
            expectedValue: 33.3);

    [Fact]
    public void NumberExpressionGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Expression("31.1 + 2.2"),
            expectedValue: 33.3);

    #endregion

    #region DataValueExpression Tests

    [Fact]
    public void DataValueExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((ValueExpression)null!);

    [Fact]
    public void DataValueExpressionGetValueForDataValueExpressionBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ValueExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: DataValue.Blank());

    [Fact]
    public void DataValueExpressionGetValueForLiteral() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ValueExpression.Literal(DataValue.Create("test")),
            expectedValue: DataValue.Create("test"));

    [Fact]
    public void DataValueExpressionGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ValueExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)),
            expectedValue: DataValue.Create("Hello World"));
    }

    [Fact]
    public void DataValueExpressionGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ValueExpression.Expression(@"""A"" & ""B"""),
            expectedValue: DataValue.Create("AB"));

    #endregion

    #region EnumExpression Tests

    [Fact]
    public void EnumExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<VariablesToClearWrapper, ArgumentNullException>((EnumExpression<VariablesToClearWrapper>)null!);

    [Fact]
    public void EnumExpressionGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<VariablesToClearWrapper, InvalidExpressionOutputTypeException>(EnumExpression<VariablesToClearWrapper>.Variable(PropertyPath.TopicVariable(Variables.BoolValue)));

    [Fact]
    public void EnumExpressionGetValueForLiteral() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            EnumExpression<VariablesToClearWrapper>.Literal(VariablesToClearWrapper.Get(VariablesToClear.ConversationScopedVariables)),
            expectedValue: VariablesToClear.ConversationScopedVariables);

    [Fact]
    public void EnumExpressionGetValueForBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            EnumExpression<VariablesToClearWrapper>.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: VariablesToClear.ConversationScopedVariables);

    [Fact]
    public void EnumExpressionGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            EnumExpression<VariablesToClearWrapper>.Variable(PropertyPath.TopicVariable(Variables.EnumValue)),
            expectedValue: VariablesToClear.ConversationScopedVariables);
    }

    [Fact]
    public void EnumExpressionGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            EnumExpression<VariablesToClearWrapper>.Expression(@"""ConversationScoped"" & ""Variables"""),
            expectedValue: VariablesToClear.ConversationScopedVariables);

    #endregion

    #region ObjectExpression Tests

    [Fact]
    public void ObjectExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<RecordDataValue, ArgumentNullException>((ObjectExpression<RecordDataValue>)null!);

    [Fact]
    public void ObjectExpressionGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<RecordDataValue, InvalidExpressionOutputTypeException>(ObjectExpression<RecordDataValue>.Variable(PropertyPath.TopicVariable(Variables.BoolValue)));

    [Fact]
    public void ObjectExpressionGetValueForLiteral()
    {
        // Arrange, Act & Assert
        RecordDataValue.Builder recordBuilder = new();
        recordBuilder.Properties.Add(nameof(EnvironmentVariableReference.SchemaName), new StringDataValue("test"));
        RecordDataValue objectRecord = recordBuilder.Build();
        _ = new EnvironmentVariableReference.Builder() { SchemaName = "test" }.Build();
        this.EvaluateExpression(
            ObjectExpression<RecordDataValue>.Literal(objectRecord),
            expectedValue: objectRecord);
    }

    [Fact]
    public void ObjectExpressionGetValueForBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ObjectExpression<RecordDataValue>.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: null);

    [Fact]
    public void ObjectExpressionGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ObjectExpression<RecordDataValue>.Variable(PropertyPath.TopicVariable(Variables.ObjectValue)),
            expectedValue: ObjectData.ToRecord());
    }

    #endregion

    #region ArrayExpression Tests

    [Fact]
    public void ArrayExpressionGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<string, ArgumentNullException>((ArrayExpression<string>)null!);

    [Fact]
    public void ArrayExpressionGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<string, InvalidExpressionOutputTypeException>(ArrayExpression<string>.Variable(PropertyPath.TopicVariable(Variables.BoolValue)));

    [Fact]
    public void ArrayExpressionGetValueForLiteral()
    {
        // Arrange, Act & Assert
        string[] input = ["a", "b"];
        this.EvaluateExpression(
            ArrayExpression<string>.Literal(input.ToImmutableArray()),
            expectedValue: input);
    }

    [Fact]
    public void ArrayExpressionGetValueForBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ArrayExpression<string>.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: []);

    [Fact]
    public void ArrayExpressionGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ArrayExpression<string>.Variable(PropertyPath.TopicVariable(Variables.ArrayValue)),
            expectedValue: ["a", "b"]);
    }

    [Fact]
    public void ArrayExpressionGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ArrayExpression<string>.Expression(@"[""a"", ""b""]"),
            expectedValue: ["a", "b"]);

    #endregion

    #region ArrayExpressionOnly Tests

    [Fact]
    public void ArrayExpressionOnlyGetValueForNull() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<string, ArgumentNullException>((ArrayExpressionOnly<string>)null!);

    [Fact]
    public void ArrayExpressionOnlyGetValueForInvalid() =>
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<string, InvalidExpressionOutputTypeException>(ArrayExpressionOnly<string>.Variable(PropertyPath.TopicVariable(Variables.BoolValue)));

    [Fact]
    public void ArrayExpressionOnlyGetValueForBlank() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ArrayExpressionOnly<string>.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: []);

    [Fact]
    public void ArrayExpressionOnlyGetValueForVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ArrayExpressionOnly<string>.Variable(PropertyPath.TopicVariable(Variables.ArrayValue)),
            expectedValue: ["a", "b"]);
    }

    [Fact]
    public void ArrayExpressionOnlyGetValueForFormula() =>
        // Arrange, Act & Assert
        this.EvaluateExpression(
            ArrayExpressionOnly<string>.Expression(@"[""a"", ""b""]"),
            expectedValue: ["a", "b"]);

    #endregion

    private EvaluationResult<bool> EvaluateExpression(BoolExpression expression, bool expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => evaluator.GetValue(expression), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(BoolExpression expression)
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private EvaluationResult<string> EvaluateExpression(StringExpression expression, string expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => evaluator.GetValue(expression), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(StringExpression expression)
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private EvaluationResult<long> EvaluateExpression(IntExpression expression, long expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => evaluator.GetValue(expression), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(IntExpression expression)
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private EvaluationResult<double> EvaluateExpression(NumberExpression expression, double expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => evaluator.GetValue(expression), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(NumberExpression expression)
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private EvaluationResult<DataValue> EvaluateExpression(ValueExpression expression, DataValue expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => evaluator.GetValue(expression), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(ValueExpression expression)
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private EvaluationResult<TEnum> EvaluateExpression<TEnum>(EnumExpression<TEnum> expression, TEnum expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        where TEnum : EnumWrapper
        => this.EvaluateExpression((evaluator) => evaluator.GetValue(expression), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TEnum, TException>(EnumExpression<TEnum> expression)
        where TEnum : EnumWrapper
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private EvaluationResult<TValue?> EvaluateExpression<TValue>(ObjectExpression<TValue> expression, TValue? expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        where TValue : BotElement
        => this.EvaluateExpression((evaluator) => evaluator.GetValue(expression), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TValue, TException>(ObjectExpression<TValue> expression)
        where TValue : BotElement
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private ImmutableArray<TValue> EvaluateExpression<TValue>(ArrayExpression<TValue> expression, TValue[] expectedValue)
        => this.EvaluateArrayExpression((evaluator) => evaluator.GetValue(expression), expectedValue);

    private void EvaluateInvalidExpression<TValue, TException>(ArrayExpression<TValue> expression)
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private ImmutableArray<TValue> EvaluateExpression<TValue>(ArrayExpressionOnly<TValue> expression, TValue[] expectedValue)
        => this.EvaluateArrayExpression((evaluator) => evaluator.GetValue(expression), expectedValue);

    private void EvaluateInvalidExpression<TValue, TException>(ArrayExpressionOnly<TValue> expression)
        where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression));

    private EvaluationResult<TValue> EvaluateExpression<TValue>(
        Func<WorkflowExpressionEngine, EvaluationResult<TValue>> evaluator,
        TValue? expectedValue,
        SensitivityLevel expectedSensitivity = SensitivityLevel.None)
    {
        // Act
        EvaluationResult<TValue> result = evaluator.Invoke(this.State.Evaluator);

        // Assert
        Assert.Equal(expectedValue, result.Value);
        Assert.Equal(expectedSensitivity, result.Sensitivity);

        return result;
    }

    private ImmutableArray<TValue> EvaluateArrayExpression<TValue>(
        Func<WorkflowExpressionEngine, ImmutableArray<TValue>> evaluator,
        TValue[] expectedValue)
    {
        // Act
        ImmutableArray<TValue> result = evaluator.Invoke(this.State.Evaluator);

        // Assert
        Assert.Equal(expectedValue.Length, result.Length);
        Assert.Equivalent(expectedValue, result);

        return result;
    }

    private void EvaluateInvalidExpression<TException>(Action<WorkflowExpressionEngine> evaluator) where TException : Exception
    {
        // Act & Assert
        Assert.Throws<TException>(() => evaluator.Invoke(this.State.Evaluator));
    }
}

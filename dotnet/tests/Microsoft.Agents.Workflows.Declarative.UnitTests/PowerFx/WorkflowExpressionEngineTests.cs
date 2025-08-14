// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Exceptions;
using Microsoft.PowerFx;
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
        public const string BlankValue = nameof(BlankValue);
    }

    public WorkflowExpressionEngineTests(ITestOutputHelper output)
        : base(output)
    {
        this.Scopes.Set(Variables.GlobalValue, WorkflowScopeType.Global, FormulaValue.New(255));
        this.Scopes.Set(Variables.BoolValue, WorkflowScopeType.Topic, FormulaValue.New(true));
        this.Scopes.Set(Variables.StringValue, WorkflowScopeType.Topic, FormulaValue.New("Hello World"));
        this.Scopes.Set(Variables.IntValue, WorkflowScopeType.Topic, FormulaValue.New(long.MaxValue));
        this.Scopes.Set(Variables.NumberValue, WorkflowScopeType.Topic, FormulaValue.New(33.3));
        this.Scopes.Set(Variables.BlankValue, WorkflowScopeType.Topic, FormulaValue.NewBlank());
    }

    #region BoolExpression Tests

    [Fact]
    public void GetValueForNullBoolExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((BoolExpression)null!);
    }

    [Fact]
    public void GetValueForInvalidBoolExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(BoolExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)));
    }

    [Fact]
    public void GetValueForBoolExpressionWithLiteral()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Literal(true),
            expectedValue: true);
    }

    [Fact]
    public void GetValueForBoolExpressionBlank()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: false);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void GetValueForBoolExpressionWithVariable(bool useState)
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Variable(PropertyPath.TopicVariable(Variables.BoolValue)),
            expectedValue: true,
            useState);
    }

    [Fact]
    public void GetValueForBoolExpressionWithFormula()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            BoolExpression.Expression("true || false"),
            expectedValue: true);
    }

    #endregion

    #region StringExpression Tests

    [Fact]
    public void GetValueForNullStringExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((StringExpression)null!);
    }

    [Fact]
    public void GetValueForInvalidStringExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(StringExpression.Variable(PropertyPath.TopicVariable(Variables.BoolValue)));
    }

    [Fact]
    public void GetValueForStringExpressionBlank()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: string.Empty);
    }

    [Fact]
    public void GetValueForStringExpressionWithLiteral()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Literal("test"),
            expectedValue: "test");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void GetValueForStringExpressionWithVariable(bool useState)
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            StringExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)),
            expectedValue: "Hello World",
            useState);
    }

    [Fact]
    public void GetValueForStringExpressionWithFormula()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            //StringExpression.Expression(@$"""{{{PropertyPath.TopicVariable(Variables.StringValue)}}}"""),
            StringExpression.Expression(@"""AB"""), // %%% IMPROVE
            expectedValue: "AB");
    }

    //[Fact]
    //public void GetValueForStringExpressionWithRecordDataValue()
    //{
    //    // Arrange
    //    RecalcEngine engine = this.CreateEngine();
    //    WorkflowExpressionEngine expressionEngine = new(engine);
    //    RecordDataValue state = new RecordDataValue();
    //    RecordDataValue globalScope = new RecordDataValue();
    //    globalScope.Properties["testValue"] = new StringDataValue("test");
    //    state.Properties["Global"] = globalScope;
    //    StringExpression expression = StringExpression.Variable(PropertyPath.Create("Global.testValue"));

    //    // Act
    //    EvaluationResult<string> result = expressionEngine.GetValue(expression, state);

    //    // Assert
    //    Assert.Equal("test", result.Value);
    //    Assert.Equal(SensitivityLevel.None, result.Sensitivity);
    //}

    #endregion

    #region IntExpression Tests

    [Fact]
    public void GetValueForNullIntExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((IntExpression)null!);
    }

    [Fact]
    public void GetValueForInvalidIntExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(IntExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)));
    }

    [Fact]
    public void GetValueForIntExpressionBlank()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: 0);
    }

    [Fact]
    public void GetValueForIntExpressionWithLiteral()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Literal(7),
            expectedValue: 7);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void GetValueForIntExpressionWithVariable(bool useState)
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Variable(PropertyPath.TopicVariable(Variables.IntValue)),
            expectedValue: long.MaxValue,
            useState);
    }

    [Fact]
    public void GetValueForIntExpressionWithFormula()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            IntExpression.Expression("1 + 6"),
            expectedValue: 7);
    }

    #endregion

    #region NumberExpression Tests

    [Fact]
    public void GetValueForNullNumberExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<ArgumentNullException>((NumberExpression)null!);
    }

    [Fact]
    public void GetValueForInvalidNumberExpression()
    {
        // Arrange, Act & Assert
        this.EvaluateInvalidExpression<InvalidExpressionOutputTypeException>(NumberExpression.Variable(PropertyPath.TopicVariable(Variables.StringValue)));
    }

    [Fact]
    public void GetValueForNumberExpressionBlank()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Variable(PropertyPath.TopicVariable(Variables.BlankValue)),
            expectedValue: 0);
    }

    [Fact]
    public void GetValueForNumberExpressionWithLiteral()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Literal(3.14),
            expectedValue: 3.14);
    }

    [Fact]
    public void GetValueForNumberExpressionWithVariable()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Variable(PropertyPath.TopicVariable(Variables.NumberValue)),
            expectedValue: 33.3);
    }

    [Fact]
    public void GetValueForNumberExpressionWithFormula()
    {
        // Arrange, Act & Assert
        this.EvaluateExpression(
            NumberExpression.Expression("31.1 + 2.2"),
            expectedValue: 33.3);
    }

    #endregion

    #region EnumExpression Tests

    //// Enum Expression Tests
    //[Fact]
    //public void GetValueForEnumExpressionWithLiteral()
    //{
    //    // Arrange
    //    RecalcEngine engine = this.CreateEngine();
    //    WorkflowExpressionEngine expressionEngine = new(engine);
    //    WorkflowScopes scopes = new();

    //    TestEnum testEnum = TestEnum.Create(TestEnumValue.Value1);
    //    EnumExpression<TestEnum> expression = new EnumExpression<TestEnum>(testEnum);

    //    // Act
    //    EvaluationResult<TestEnum> result = expressionEngine.GetValue(expression, scopes);

    //    // Assert
    //    Assert.Equal(TestEnumValue.Value1, result.Value.Value);
    //    Assert.Equal(SensitivityLevel.None, result.Sensitivity);
    //}

    #endregion

    //// Object Expression Tests
    //[Fact]
    //public void GetValueForObjectExpressionWithLiteral()
    //{
    //    // Arrange
    //    RecalcEngine engine = this.CreateEngine();
    //    WorkflowExpressionEngine expressionEngine = new(engine);
    //    WorkflowScopes scopes = new();
    //    TestBotElement testElement = new TestBotElement { Name = "Test" };
    //    ObjectExpression<TestBotElement> expression = new ObjectExpression<TestBotElement>(testElement);

    //    // Act
    //    EvaluationResult<TestBotElement?> result = expressionEngine.GetValue(expression, scopes);

    //    // Assert
    //    Assert.NotNull(result.Value);
    //    Assert.Equal("Test", result.Value.Name);
    //    Assert.Equal(SensitivityLevel.None, result.Sensitivity);
    //}

    //// Array Expression Tests
    //[Fact]
    //public void GetValueForArrayExpressionWithLiteral()
    //{
    //    // Arrange
    //    RecalcEngine engine = this.CreateEngine();
    //    WorkflowExpressionEngine expressionEngine = new(engine);
    //    WorkflowScopes scopes = new();

    //    ImmutableArray<string> array = ImmutableArray.Create("item1", "item2");
    //    ArrayExpression<string> expression = new ArrayExpression<string>(array);

    //    // Act
    //    ImmutableArray<string> result = expressionEngine.GetValue(expression, scopes);

    //    // Assert
    //    Assert.Equal(2, result.Length);
    //    Assert.Equal("item1", result[0]);
    //    Assert.Equal("item2", result[1]);
    //}

    private EvaluationResult<bool> EvaluateExpression(BoolExpression expression, bool expectedValue, bool useState = false, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => useState ? evaluator.GetValue(expression, this.Scopes) : evaluator.GetValue(expression, this.Scopes.BuildState()), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(BoolExpression expression) where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression, this.Scopes));

    private EvaluationResult<string> EvaluateExpression(StringExpression expression, string expectedValue, bool useState = false, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => useState ? evaluator.GetValue(expression, this.Scopes) : evaluator.GetValue(expression, this.Scopes.BuildState()), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(StringExpression expression) where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression, this.Scopes));

    private EvaluationResult<long> EvaluateExpression(IntExpression expression, long expectedValue, bool useState = false, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => useState ? evaluator.GetValue(expression, this.Scopes) : evaluator.GetValue(expression, this.Scopes.BuildState()), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(IntExpression expression) where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression, this.Scopes));

    private EvaluationResult<double> EvaluateExpression(NumberExpression expression, double expectedValue, bool useState = false, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        => this.EvaluateExpression((evaluator) => useState ? evaluator.GetValue(expression, this.Scopes) : evaluator.GetValue(expression, this.Scopes.BuildState()), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TException>(NumberExpression expression) where TException : Exception
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue(expression, this.Scopes));

    private EvaluationResult<TEnum> EvaluateExpression<TEnum>(EnumExpression<TEnum> expression, TEnum expectedValue, bool useState = false, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
        where TEnum : EnumWrapper
        => this.EvaluateExpression((evaluator) => useState ? evaluator.GetValue<TEnum>(expression, this.Scopes) : evaluator.GetValue<TEnum>(expression, this.Scopes.BuildState()), expectedValue, expectedSensitivity);

    private void EvaluateInvalidExpression<TEnum, TException>(EnumExpression<TEnum> expression) where TException : Exception where TEnum : EnumWrapper
        => this.EvaluateInvalidExpression<TException>((evaluator) => evaluator.GetValue<TEnum>(expression, this.Scopes));

    //private EvaluationResult<TValue> EvaluateExpression<TValue>(ObjectExpression<TValue> expression, TValue expectedValue, SensitivityLevel expectedSensitivity = SensitivityLevel.None)
    //    => this.EvaluateExpression((evaluator) => evaluator.GetValue<TValue>(expression, this.Scopes), expectedValue, expectedSensitivity);

    private EvaluationResult<TValue> EvaluateExpression<TValue>(
        Func<WorkflowExpressionEngine, EvaluationResult<TValue>> evaluator,
        TValue expectedValue,
        SensitivityLevel expectedSensitivity = SensitivityLevel.None)
    {
        // Arrange
        RecalcEngine engine = this.CreateEngine();
        WorkflowExpressionEngine expressionEngine = new(engine);

        // Act
        EvaluationResult<TValue> result = evaluator.Invoke(expressionEngine);

        // Assert
        Assert.Equal(expectedValue, result.Value);
        Assert.Equal(expectedSensitivity, result.Sensitivity);

        return result;
    }

    private void EvaluateInvalidExpression<TException>(Action<WorkflowExpressionEngine> evaluator) where TException : Exception
    {
        // Arrange
        RecalcEngine engine = this.CreateEngine();
        WorkflowExpressionEngine expressionEngine = new(engine);

        // Act
        Assert.Throws<TException>(() => evaluator.Invoke(expressionEngine));
    }
}

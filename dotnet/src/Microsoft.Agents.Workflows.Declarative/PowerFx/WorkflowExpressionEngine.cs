// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Exceptions;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

internal class WorkflowExpressionEngine : IExpressionEngine
{
    private readonly RecalcEngine _engine;

    public WorkflowExpressionEngine(RecalcEngine engine)
    {
        this._engine = engine;
    }

    public EvaluationResult<bool> GetValue(BoolExpression boolean, WorkflowScopes? state = null) => this.GetValue(boolean, state, this.EvaluateScope);

    public EvaluationResult<bool> GetValue(BoolExpression boolean, RecordDataValue state) => this.GetValue(boolean, state, this.EvaluateState);

    public EvaluationResult<string> GetValue(StringExpression expression, WorkflowScopes? state = null) => this.GetValue(expression, state, this.EvaluateScope);

    public EvaluationResult<string> GetValue(StringExpression expression, RecordDataValue state) => this.GetValue(expression, state, this.EvaluateState);

    public EvaluationResult<DataValue> GetValue(ValueExpression expression, WorkflowScopes? state = null) => this.GetValue(expression, state, this.EvaluateScope);

    public EvaluationResult<DataValue> GetValue(ValueExpression expression, RecordDataValue state) => this.GetValue(expression, state, this.EvaluateState);

    public EvaluationResult<long> GetValue(IntExpression expression, WorkflowScopes? state = null) => this.GetValue(expression, state, this.EvaluateScope);

    public EvaluationResult<long> GetValue(IntExpression expression, RecordDataValue state) => this.GetValue(expression, state, this.EvaluateState);

    public EvaluationResult<double> GetValue(NumberExpression expression, WorkflowScopes? state = null) => this.GetValue(expression, state, this.EvaluateScope);

    public EvaluationResult<double> GetValue(NumberExpression expression, RecordDataValue state) => this.GetValue(expression, state, this.EvaluateState);

    public EvaluationResult<TValue?> GetValue<TValue>(ObjectExpression<TValue> expression, WorkflowScopes? state = null) where TValue : BotElement => this.GetValue(expression, state, this.EvaluateScope);

    public EvaluationResult<TValue?> GetValue<TValue>(ObjectExpression<TValue> expression, RecordDataValue state) where TValue : BotElement => this.GetValue(expression, state, this.EvaluateState);

    public ImmutableArray<T> GetValue<T>(ArrayExpression<T> expression, WorkflowScopes? state = null) => this.GetValue(expression, state, this.EvaluateScope).Value;

    public ImmutableArray<T> GetValue<T>(ArrayExpression<T> expression, RecordDataValue state) => this.GetValue(expression, state, this.EvaluateState).Value;

    public ImmutableArray<T> GetValue<T>(ArrayExpressionOnly<T> expression, WorkflowScopes? state = null) => this.GetValue(expression, state, this.EvaluateScope).Value;

    public ImmutableArray<T> GetValue<T>(ArrayExpressionOnly<T> expression, RecordDataValue state) => this.GetValue(expression, state, this.EvaluateState).Value;

    public EvaluationResult<TValue> GetValue<TValue>(EnumExpression<TValue> expression, WorkflowScopes? state = null) where TValue : EnumWrapper =>
        this.GetValue<TValue, WorkflowScopes>(expression, state, this.EvaluateScope);

    public EvaluationResult<TValue> GetValue<TValue>(EnumExpression<TValue> expression, RecordDataValue state) where TValue : EnumWrapper =>
        this.GetValue<TValue, RecordDataValue>(expression, state, this.EvaluateState);

    public DialogSchemaName GetValue(DialogExpression expression, RecordDataValue state)
    {
        throw new NotSupportedException();
    }

    public EvaluationResult<string> GetValue(AdaptiveCardExpression expression, RecordDataValue state)
    {
        throw new NotSupportedException();
    }

    public EvaluationResult<FileDataValue?> GetValue(FileExpression expression, RecordDataValue state)
    {
        throw new NotSupportedException();
    }

    private EvaluationResult<bool> GetValue<TState>(BoolExpression expression, TState state, Func<ExpressionBase, TState, EvaluationResult<FormulaValue>> evaluator)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<bool>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        if (expressionResult.Value is BlankValue)
        {
            return new EvaluationResult<bool>(default, SensitivityLevel.None);
        }

        if (expressionResult.Value is not BooleanValue formulaValue)
        {
            throw new InvalidExpressionOutputTypeException(expressionResult.Value.GetDataType(), DataType.Boolean);
        }

        return new EvaluationResult<bool>(formulaValue.Value, expressionResult.Sensitivity);
    }

    private EvaluationResult<string> GetValue<TState>(StringExpression expression, TState state, Func<ExpressionBase, TState, EvaluationResult<FormulaValue>> evaluator)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<string>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        if (expressionResult.Value is BlankValue)
        {
            return new EvaluationResult<string>(string.Empty, expressionResult.Sensitivity);
        }

        if (expressionResult.Value is RecordValue recordValue)
        {
            return new EvaluationResult<string>(recordValue.Format(), expressionResult.Sensitivity);
        }

        if (expressionResult.Value is not StringValue formulaValue)
        {
            throw new InvalidExpressionOutputTypeException(expressionResult.Value.GetDataType(), DataType.String);
        }

        return new EvaluationResult<string>(formulaValue.Value, expressionResult.Sensitivity);
    }

    private EvaluationResult<long> GetValue<TState>(IntExpression expression, TState state, Func<ExpressionBase, TState, EvaluationResult<FormulaValue>> evaluator)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<long>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        if (expressionResult.Value is BlankValue)
        {
            return new EvaluationResult<long>(default, expressionResult.Sensitivity);
        }

        if (expressionResult.Value is not DecimalValue formulaValue)
        {
            throw new InvalidExpressionOutputTypeException(expressionResult.Value.GetDataType(), DataType.Number);
        }

        return new EvaluationResult<long>(Convert.ToInt64(formulaValue.Value), expressionResult.Sensitivity);
    }

    private EvaluationResult<double> GetValue<TState>(NumberExpression expression, TState state, Func<ExpressionBase, TState, EvaluationResult<FormulaValue>> evaluator)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<double>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        if (expressionResult.Value is BlankValue)
        {
            return new EvaluationResult<double>(default, expressionResult.Sensitivity);
        }

        if (expressionResult.Value is DecimalValue decimalValue)
        {
            return new EvaluationResult<double>(Convert.ToDouble(decimalValue.Value), expressionResult.Sensitivity);
        }

        if (expressionResult.Value is not NumberValue formulaValue)
        {
            throw new InvalidExpressionOutputTypeException(expressionResult.Value.GetDataType(), DataType.Float);
        }

        return new EvaluationResult<double>(formulaValue.Value, expressionResult.Sensitivity);
    }

    private EvaluationResult<DataValue> GetValue<TState>(ValueExpression expression, TState? state, Func<ExpressionBase, TState?, EvaluationResult<FormulaValue>> evaluator)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<DataValue>(expression.LiteralValue ?? BlankDataValue.Instance, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        return new EvaluationResult<DataValue>(expressionResult.Value.ToDataValue(), expressionResult.Sensitivity);
    }

    private EvaluationResult<TValue> GetValue<TValue, TState>(EnumExpression<TValue> expression, TState? state, Func<ExpressionBase, TState?, EvaluationResult<FormulaValue>> evaluator) where TValue : EnumWrapper
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<TValue>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        return expressionResult.Value switch
        {
            BlankValue => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>(0), expressionResult.Sensitivity),
            StringValue s when s.Value is not null => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>(s.Value), expressionResult.Sensitivity),
            StringValue => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>(0), expressionResult.Sensitivity),
            NumberValue number => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>((int)number.Value), expressionResult.Sensitivity),
            _ => throw new InvalidExpressionOutputTypeException(expressionResult.Value.GetDataType(), DataType.String),
        };
    }

    private EvaluationResult<TValue?> GetValue<TValue, TState>(ObjectExpression<TValue> expression, TState state, Func<ExpressionBase, TState, EvaluationResult<FormulaValue>> evaluator) where TValue : BotElement
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.LiteralValue != null)
        {
            return new EvaluationResult<TValue?>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        if (expressionResult.Value is BlankValue)
        {
            return new EvaluationResult<TValue?>(null, expressionResult.Sensitivity);
        }

        if (expressionResult.Value is not RecordValue formulaValue)
        {
            throw new InvalidExpressionOutputTypeException(expressionResult.Value.GetDataType(), DataType.TableFromEnumerable<TValue>());
        }

        try
        {
            return new EvaluationResult<TValue?>(ObjectExpressionParser<TValue>.Parse(formulaValue.ToRecord()), expressionResult.Sensitivity);
        }
        catch (Exception exception)
        {
            throw new CannotParseObjectExpressionOutputException(typeof(TValue), exception);
        }
    }

    private EvaluationResult<ImmutableArray<TValue>> GetValue<TState, TValue>(ArrayExpression<TValue> expression, TState state, Func<ExpressionBase, TState, EvaluationResult<FormulaValue>> evaluator)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<ImmutableArray<TValue>>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        return new EvaluationResult<ImmutableArray<TValue>>(ParseArrayResults<TValue>(expressionResult.Value), expressionResult.Sensitivity);
    }

    private EvaluationResult<ImmutableArray<TValue>> GetValue<TState, TValue>(ArrayExpressionOnly<TValue> expression, TState state, Func<ExpressionBase, TState, EvaluationResult<FormulaValue>> evaluator)
    {
        Throw.IfNull(expression, nameof(expression));

        EvaluationResult<FormulaValue> expressionResult = evaluator.Invoke(expression, state);

        return new EvaluationResult<ImmutableArray<TValue>>(ParseArrayResults<TValue>(expressionResult.Value), expressionResult.Sensitivity);
    }

    private static ImmutableArray<TValue> ParseArrayResults<TValue>(FormulaValue value)
    {
        if (value is BlankValue)
        {
            return ImmutableArray<TValue>.Empty;
        }

        if (value is not TableValue tableValue)
        {
            throw new InvalidExpressionOutputTypeException(value.GetDataType(), DataType.TableFromEnumerable<TValue>());
        }

        TableDataValue tableDataValue = tableValue.ToTable();
        try
        {
            List<TValue> list = [];
            foreach (RecordDataValue row in tableDataValue.Values)
            {
                TValue? s = TableItemParser<TValue>.Parse(row);
                if (s != null)
                {
                    list.Add(s);
                }
            }
            return list.ToImmutableArray();
        }
        catch (Exception exception)
        {
            throw new CannotParseObjectExpressionOutputException(typeof(TValue), exception);
        }
    }

    private EvaluationResult<FormulaValue> EvaluateState(ExpressionBase expression, RecordDataValue? state)
    {
        if (state is not null)
        {
            foreach (KeyValuePair<string, DataValue> kvp in state.Properties)
            {
                if (kvp.Value is RecordDataValue scopeRecord)
                {
                    Bind(kvp.Key, scopeRecord.ToRecordValue());
                }
            }
        }

        return this.Evaluate(expression);

        void Bind(string scopeName, RecordValue stateRecord)
        {
            this._engine.DeleteFormula(scopeName);
            this._engine.UpdateVariable(scopeName, stateRecord);
        }
    }

    private EvaluationResult<FormulaValue> EvaluateScope(ExpressionBase expression, WorkflowScopes? state = null)
    {
        state?.Bind(this._engine);

        return this.Evaluate(expression);
    }

    private EvaluationResult<FormulaValue> Evaluate(ExpressionBase expression)
    {
        string? expressionText =
            expression.IsVariableReference ?
            expression.VariableReference?.Format() :
            expression.ExpressionText;

        return new(this._engine.Eval(expressionText), SensitivityLevel.None);
    }
}

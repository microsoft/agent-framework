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

internal sealed class WorkflowExpressionEngine
{
    private readonly RecalcEngine _engine;

    public WorkflowExpressionEngine(RecalcEngine engine)
    {
        this._engine = engine;
    }

    public EvaluationResult<bool> GetValue(BoolExpression boolean) => this.Evaluate(boolean);

    public EvaluationResult<string> GetValue(StringExpression expression) => this.Evaluate(expression);

    public EvaluationResult<DataValue> GetValue(ValueExpression expression) => this.Evaluate(expression);

    public EvaluationResult<long> GetValue(IntExpression expression) => this.Evaluate(expression);

    public EvaluationResult<double> GetValue(NumberExpression expression) => this.Evaluate(expression);

    public EvaluationResult<TValue?> GetValue<TValue>(ObjectExpression<TValue> expression) where TValue : BotElement => this.Evaluate(expression);

    public ImmutableArray<T> GetValue<T>(ArrayExpression<T> expression) => this.Evaluate(expression).Value;

    public ImmutableArray<T> GetValue<T>(ArrayExpressionOnly<T> expression) => this.Evaluate(expression).Value;

    public EvaluationResult<TValue> GetValue<TValue>(EnumExpression<TValue> expression) where TValue : EnumWrapper =>
        this.Evaluate(expression);

    private EvaluationResult<bool> Evaluate(BoolExpression expression)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<bool>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

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

    private EvaluationResult<string> Evaluate(StringExpression expression)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<string>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

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

    private EvaluationResult<long> Evaluate(IntExpression expression)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<long>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

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

    private EvaluationResult<double> Evaluate(NumberExpression expression)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<double>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

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

    private EvaluationResult<DataValue> Evaluate(ValueExpression expression)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<DataValue>(expression.LiteralValue ?? BlankDataValue.Instance, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

        return new EvaluationResult<DataValue>(expressionResult.Value.ToDataValue(), expressionResult.Sensitivity);
    }

    private EvaluationResult<TValue> Evaluate<TValue>(EnumExpression<TValue> expression) where TValue : EnumWrapper
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<TValue>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

        return expressionResult.Value switch
        {
            BlankValue => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>(0), expressionResult.Sensitivity),
            StringValue s when s.Value is not null => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>(s.Value), expressionResult.Sensitivity),
            StringValue => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>(0), expressionResult.Sensitivity),
            NumberValue number => new EvaluationResult<TValue>(EnumWrapper.Create<TValue>((int)number.Value), expressionResult.Sensitivity),
            _ => throw new InvalidExpressionOutputTypeException(expressionResult.Value.GetDataType(), DataType.String),
        };
    }

    private EvaluationResult<TValue?> Evaluate<TValue>(ObjectExpression<TValue> expression) where TValue : BotElement
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.LiteralValue is not null)
        {
            return new EvaluationResult<TValue?>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

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

    private EvaluationResult<ImmutableArray<TValue>> Evaluate<TValue>(ArrayExpression<TValue> expression)
    {
        Throw.IfNull(expression, nameof(expression));

        if (expression.IsLiteral)
        {
            return new EvaluationResult<ImmutableArray<TValue>>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

        return new EvaluationResult<ImmutableArray<TValue>>(ParseArrayResults<TValue>(expressionResult.Value), expressionResult.Sensitivity);
    }

    private EvaluationResult<ImmutableArray<TValue>> Evaluate<TValue>(ArrayExpressionOnly<TValue> expression)
    {
        Throw.IfNull(expression, nameof(expression));

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

        return new EvaluationResult<ImmutableArray<TValue>>(ParseArrayResults<TValue>(expressionResult.Value), expressionResult.Sensitivity);
    }

    private static ImmutableArray<TValue> ParseArrayResults<TValue>(FormulaValue value)
    {
        if (value is BlankValue)
        {
            return [];
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
                if (TableItemParser<TValue>.Parse(row) is TValue s)
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

    private EvaluationResult<FormulaValue> EvaluateScope(ExpressionBase expression)
    {
        string? expressionText =
            expression.IsVariableReference ?
            expression.VariableReference?.ToString() :
            expression.ExpressionText;

        return new(this._engine.Eval(expressionText), SensitivityLevel.None);
    }
}

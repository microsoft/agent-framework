// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Agents.ObjectModel.Exceptions;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Syntax;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.PowerFx;

internal sealed class WorkflowExpressionEngine
{
    private readonly WorkflowFormulaState _state;

    public WorkflowExpressionEngine(WorkflowFormulaState state)
    {
        this._state = state;
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

    public EvaluationResult<string> Format(IEnumerable<TemplateLine> template)
    {
        Throw.IfNull(template);

        SensitivityLevel sensitivity = SensitivityLevel.None;
        List<string> segments = [];
        foreach (EvaluationResult<string> result in template.Select(this.Format))
        {
            sensitivity = MaxSensitivity(sensitivity, result.Sensitivity);
            segments.Add(result.Value);
        }

        return new(string.Concat(segments), sensitivity);
    }

    public EvaluationResult<string> Format(TemplateLine? line)
    {
        if (line is null)
        {
            return new(string.Empty, SensitivityLevel.None);
        }

        SensitivityLevel sensitivity = SensitivityLevel.None;
        List<string> segments = [];
        foreach (EvaluationResult<string> result in line.Segments.Select(this.Format))
        {
            sensitivity = MaxSensitivity(sensitivity, result.Sensitivity);
            segments.Add(result.Value);
        }

        return new(string.Concat(segments), sensitivity);
    }

    private EvaluationResult<string> Format(TemplateSegment segment)
    {
        if (segment is TextSegment textSegment)
        {
            return new(textSegment.Value ?? string.Empty, SensitivityLevel.None);
        }

        if (segment is ExpressionSegment { Expression: not null } expressionSegment)
        {
            EvaluationResult<FormulaValue> result = this.EvaluateScope(expressionSegment.Expression);
            return new(result.Value.Format(), result.Sensitivity);
        }

        throw new DeclarativeModelException($"Unsupported segment type: {segment.GetType().Name}");
    }

    private EvaluationResult<bool> Evaluate(BoolExpression expression)
    {
        Throw.IfNull(expression);

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
        Throw.IfNull(expression);

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
        Throw.IfNull(expression);

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
        Throw.IfNull(expression);

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
        Throw.IfNull(expression);

        if (expression.IsLiteral)
        {
            return new EvaluationResult<DataValue>(expression.LiteralValue ?? BlankDataValue.Instance, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

        return new EvaluationResult<DataValue>(expressionResult.Value.ToDataValue(), expressionResult.Sensitivity);
    }

    private EvaluationResult<TValue> Evaluate<TValue>(EnumExpression<TValue> expression) where TValue : EnumWrapper
    {
        Throw.IfNull(expression);

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
        Throw.IfNull(expression);

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
        Throw.IfNull(expression);

        if (expression.IsLiteral)
        {
            return new EvaluationResult<ImmutableArray<TValue>>(expression.LiteralValue, SensitivityLevel.None);
        }

        EvaluationResult<FormulaValue> expressionResult = this.EvaluateScope(expression);

        return new EvaluationResult<ImmutableArray<TValue>>(ParseArrayResults<TValue>(expressionResult.Value), expressionResult.Sensitivity);
    }

    private EvaluationResult<ImmutableArray<TValue>> Evaluate<TValue>(ArrayExpressionOnly<TValue> expression)
    {
        Throw.IfNull(expression);

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

        FormulaValue result = this._state.Engine.Eval(expressionText);

        if (result is ErrorValue errorValue)
        {
            throw new DeclarativeActionException(errorValue.Format());
        }

        return new(result, this.GetSensitivity(expression));
    }

    private SensitivityLevel GetSensitivity(ExpressionBase expression)
    {
        if (expression.VariableReference is { VariableName: string variableName })
        {
            return this._state.GetSensitivity(variableName, expression.VariableReference.NamespaceAlias);
        }

        string? expressionText = expression.ExpressionText;
        if (string.IsNullOrWhiteSpace(expressionText))
        {
            return SensitivityLevel.None;
        }

        CheckResult checkResult = this._state.Engine.Check(expressionText);
        checkResult.ThrowOnErrors();

        SensitivityLevel sensitivity = SensitivityLevel.None;
        foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(checkResult.Parse.Root))
        {
            sensitivity = MaxSensitivity(sensitivity, this._state.GetSensitivity(reference.VariableName, reference.ScopeName));
        }

        return sensitivity;
    }

    private static IEnumerable<(string? ScopeName, string VariableName)> GetVariableReferences(TexlNode node)
    {
        switch (node)
        {
            case DottedNameNode dottedNameNode:
                if (TryGetDottedReference(dottedNameNode, out (string? ScopeName, string VariableName) dottedReference))
                {
                    yield return dottedReference;
                }
                else
                {
                    foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(dottedNameNode.Left))
                    {
                        yield return reference;
                    }
                }
                yield break;

            case FirstNameNode firstNameNode:
                yield return (null, firstNameNode.Ident.Name.Value);
                yield break;

            case AsNode asNode:
                foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(asNode.Left))
                {
                    yield return reference;
                }
                yield break;

            case BinaryOpNode binaryOpNode:
                foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(binaryOpNode.Left))
                {
                    yield return reference;
                }
                foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(binaryOpNode.Right))
                {
                    yield return reference;
                }
                yield break;

            case UnaryOpNode unaryOpNode:
                foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(unaryOpNode.Child))
                {
                    yield return reference;
                }
                yield break;

            case CallNode callNode:
                foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(callNode.Args))
                {
                    yield return reference;
                }
                yield break;

            case VariadicBase variadicBase:
                foreach (TexlNode childNode in variadicBase.ChildNodes)
                {
                    foreach ((string? ScopeName, string VariableName) reference in GetVariableReferences(childNode))
                    {
                        yield return reference;
                    }
                }
                yield break;
        }
    }

    private static bool TryGetDottedReference(DottedNameNode dottedNameNode, out (string? ScopeName, string VariableName) reference)
    {
        List<string> names = [];
        TexlNode node = dottedNameNode;
        while (node is DottedNameNode current)
        {
            names.Add(current.Right.Name.Value);
            node = current.Left;
        }

        if (node is not FirstNameNode firstNameNode)
        {
            reference = default;
            return false;
        }

        names.Add(firstNameNode.Ident.Name.Value);
        names.Reverse();
        reference = names.Count > 1 && VariableScopeNames.IsValidName(names[0])
            ? (names[0], names[1])
            : (null, names[0]);
        return true;
    }

    private static SensitivityLevel MaxSensitivity(SensitivityLevel left, SensitivityLevel right) =>
        left == SensitivityLevel.Sensitive || right == SensitivityLevel.Sensitive ? SensitivityLevel.Sensitive : SensitivityLevel.None;
}

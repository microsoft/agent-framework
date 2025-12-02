// Copyright (c) Microsoft. All rights reserved.

using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="BoolExpression"/>.
/// </summary>
internal static class BoolExpressionExtensions
{
    /// <summary>
    /// Evaluates the given <see cref="BoolExpression"/> using the provided <see cref="RecalcEngine"/>.
    /// </summary>
    /// <param name="expression">Expression to evaluate.</param>
    /// <param name="engine">Recalc engine to use for evaluation.</param>
    /// <returns>The evaluated boolean value, or null if the expression is null or cannot be evaluated.</returns>
    internal static bool? Eval(this BoolExpression? expression, RecalcEngine? engine)
    {
        if (expression is null)
        {
            return null;
        }

        if (expression.IsLiteral)
        {
            return expression.LiteralValue;
        }

        if (engine is null)
        {
            return null;
        }

        if (expression.IsExpression)
        {
            return engine.Eval(expression.ExpressionText!).AsBoolean();
        }
        else if (expression.IsVariableReference)
        {
            var formulaValue = engine.Eval(expression.VariableReference!.VariableName);
            if (formulaValue is BooleanValue booleanValue)
            {
                return booleanValue.Value;
            }

            if (formulaValue is StringValue stringValue && bool.TryParse(stringValue.Value, out bool result))
            {
                return result;
            }
        }

        return null;
    }
}

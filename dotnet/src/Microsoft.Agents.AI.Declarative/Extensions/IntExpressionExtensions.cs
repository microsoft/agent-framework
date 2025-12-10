// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="IntExpression"/>.
/// </summary>
internal static class IntExpressionExtensions
{
    /// <summary>
    /// Evaluates the given <see cref="IntExpression"/> using the provided <see cref="RecalcEngine"/>.
    /// </summary>
    /// <param name="expression">Expression to evaluate.</param>
    /// <param name="engine">Recalc engine to use for evaluation.</param>
    /// <returns>The evaluated integer value, or null if the expression is null or cannot be evaluated.</returns>
    internal static long? Eval(this IntExpression? expression, RecalcEngine? engine)
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
            return (long)engine.Eval(expression.ExpressionText!).AsDouble();
        }
        else if (expression.IsVariableReference)
        {
            var formulaValue = engine.Eval(expression.VariableReference!.VariableName);
            if (formulaValue is NumberValue numberValue)
            {
                return (long)numberValue.Value;
            }

            if (formulaValue is StringValue stringValue && int.TryParse(stringValue.Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int result))
            {
                return result;
            }
        }

        return null;
    }
}

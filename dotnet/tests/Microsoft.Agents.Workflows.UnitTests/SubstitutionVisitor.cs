// Copyright (c) Microsoft. All rights reserved.

using System.Linq.Expressions;

namespace Microsoft.Agents.Workflows.UnitTests;

internal sealed class SubstitutionVisitor(ParameterExpression parameter, Expression substitution) : ExpressionVisitor
{
    private ParameterExpression Parameter => parameter;
    private Expression Substitution => substitution;

    protected override Expression VisitParameter(ParameterExpression node)
    {
        if (node.Name == this.Parameter.Name)
        {
            return this.Substitution;
        }

        return base.VisitParameter(node);
    }
}

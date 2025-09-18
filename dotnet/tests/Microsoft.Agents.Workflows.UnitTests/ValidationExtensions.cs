// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Linq;
using System.Linq.Expressions;
using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.UnitTests;

internal static partial class ValidationExtensions
{
    public static Expression<Func<EdgeConnection, bool>> CreateValidator(this EdgeConnection prototype)
    {
        return actual => actual.SourceIds.Count == prototype.SourceIds.Count &&
                         actual.SinkIds.Count == prototype.SinkIds.Count &&
                         prototype.SourceIds.SequenceEqual(actual.SourceIds) &&
                         prototype.SinkIds.SequenceEqual(actual.SinkIds);
    }

    public static Expression<Func<TypeId, bool>> CreateValidator(this TypeId prototype)
    {
        return actual => actual.AssemblyName == prototype.AssemblyName &&
                         actual.TypeName == prototype.TypeName;
    }

    public static Expression<Func<ExecutorInfo, bool>> CreateValidator(this ExecutorInfo prototype)
    {
        return actual => actual.ExecutorId == prototype.ExecutorId &&
                         // Rely on the TypeId test to probe TypeId serialization - just validate that we got a functional TypeId
                         actual.ExecutorType.Equals(prototype.ExecutorType);
    }

    public static Expression<Func<InputPortInfo, bool>> CreatePortInfoValidator(this InputPort prototype)
    {
        return actual => actual.PortId == prototype.Id &&
                         // Rely on the TypeId test to probe TypeId serialization - just validate that we got a functional TypeId
                         actual.RequestType.IsMatch(prototype.Request) &&
                         actual.ResponseType.IsMatch(prototype.Response);
    }

    public static Expression<Func<DirectEdgeInfo, bool>> CreateValidator(this DirectEdgeInfo prototype)
    {
        return actual => actual.Connection == prototype.Connection &&
                         actual.HasCondition == prototype.HasCondition;
    }

    public static Expression<Func<FanOutEdgeInfo, bool>> CreateValidator(this FanOutEdgeInfo prototype)
    {
        return actual => actual.Connection == prototype.Connection &&
                         actual.HasAssigner == prototype.HasAssigner;
    }

    public static Expression<Func<FanInEdgeInfo, bool>> CreateValidator(this FanInEdgeInfo prototype)
    {
        return actual => actual.Connection == prototype.Connection;
    }

    public static Expression<Func<EdgeInfo, bool>> CreatePolyValidator(this EdgeInfo prototype)
    {
        switch (prototype.Kind)
        {
            case EdgeKind.Direct:
            {
                var innerValidatorExpr = CreateValidator((DirectEdgeInfo)prototype);

                // Check that incoming is of the correct type, and if so, chain to the body
                Debug.Assert(innerValidatorExpr.Parameters.Count == 1, "Validator is of unexpected arity");

                return CreateValidatorExpression(innerValidatorExpr);
            }
            case EdgeKind.FanOut:
            {
                var innerValidatorExpr = CreateValidator((FanOutEdgeInfo)prototype);

                // Check that incoming is of the correct type, and if so, chain to the body
                Debug.Assert(innerValidatorExpr.Parameters.Count == 1, "Validator is of unexpected arity");

                return CreateValidatorExpression(innerValidatorExpr);
            }
            case EdgeKind.FanIn:
            {
                var innerValidatorExpr = CreateValidator((FanInEdgeInfo)prototype);

                // Check that incoming is of the correct type, and if so, chain to the body
                Debug.Assert(innerValidatorExpr.Parameters.Count == 1, "Validator is of unexpected arity");

                return CreateValidatorExpression(innerValidatorExpr);
            }
            default:
                throw new NotSupportedException($"Unsupported edge type: {prototype.Kind}");
        }

        Expression<Func<EdgeInfo, bool>> CreateValidatorExpression<TInner>(Expression<Func<TInner, bool>> innerValidator)
            where TInner : EdgeInfo
        {
            var innerParam = innerValidator.Parameters[0];
            var innerBody = innerValidator.Body;

            var outerParam = Expression.Parameter(typeof(EdgeInfo), "actual");
            var convertExpr = Expression.Convert(outerParam, typeof(TInner));

            ExpressionVisitor visitor = new SubstitutionVisitor(innerParam, convertExpr);
            Expression innerValidatorExpr = visitor.Visit(innerBody);

            BinaryExpression bodyExpression = Expression.AndAlso(
                        Expression.AndAlso(
                            Expression.Equal(
                                Expression.Property(outerParam, nameof(EdgeInfo.Kind)),
                                Expression.Constant(prototype.Kind)
                            ),
                            Expression.TypeIs(outerParam, typeof(TInner))
                        ),
                        innerValidatorExpr
                    );

            return Expression.Lambda<Func<EdgeInfo, bool>>(
                bodyExpression,
                outerParam);
        }
    }

    public static Expression<Func<ScopeId, bool>> CreateValidator(this ScopeId prototype)
    {
        return actual => actual.ExecutorId == prototype.ExecutorId &&
                         actual.ScopeName == prototype.ScopeName;
    }

    public static Expression<Func<ScopeKey, bool>> CreateValidator(this ScopeKey prototype)
    {
        return actual => actual.Key == prototype.Key &&
                         actual.ScopeId.ScopeName == prototype.ScopeId.ScopeName &&
                         actual.ScopeId.ExecutorId == prototype.ScopeId.ExecutorId;
    }

    public static Expression<Func<ExecutorIdentity, bool>> CreateValidator(this ExecutorIdentity prototype)
    {
        return actual => actual.Id == prototype.Id;
    }

    public static Expression<Func<ExternalRequest, bool>> CreateValidator(this ExternalRequest prototype)
    {
        return actual => actual.RequestId == prototype.RequestId &&
                         actual.PortInfo == prototype.PortInfo &&
                         actual.Data == prototype.Data;
    }

    public static Expression<Func<ExternalResponse, bool>> CreateValidator(this ExternalResponse prototype)
    {
        return actual => actual.RequestId == prototype.RequestId &&
                         actual.Data == prototype.Data;
    }

    public static Expression<Func<ChatMessage, bool>> CreateValidatorCheckingText(this ChatMessage prototype)
    {
        return actual => actual.Role == prototype.Role &&
                         actual.AuthorName == prototype.AuthorName &&
                         actual.CreatedAt == prototype.CreatedAt &&
                         actual.MessageId == prototype.MessageId &&
                         actual.Text == prototype.Text;
    }
}

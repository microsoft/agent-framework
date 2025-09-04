// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Builder for converting a Foundry workflow object-model YAML definition into a process.
/// </summary>
/// <typeparam name="TInput">The type of the input message</typeparam>
public class DeclarativeWorkflowBuilder<TInput> : WorkflowBuilder where TInput : notnull
{
    /// <summary>
    /// Builds a process from the provided YAML definition of a CPS Topic ObjectModel.
    /// </summary>
    /// <param name="workflowId">The unique ID of the workflow.</param>
    /// <param name="options">The execution context for the workflow.</param>
    /// <param name="inputTransform">An optional function to transform the input message into a <see cref="ChatMessage"/>.</param>
    /// <returns></returns>
    public DeclarativeWorkflowBuilder(
        string workflowId,
        DeclarativeWorkflowOptions options,
        Func<TInput, ChatMessage>? inputTransform = null)
        : this(CreateExecutor(workflowId, options, inputTransform))
    {
    }

    private DeclarativeWorkflowBuilder(
        Executor rootExecutor)
        : base(rootExecutor)
    {
        this.Root = rootExecutor;
    }

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public Executor Root { get; }

    private static DeclarativeWorkflowExecutor<TInput> CreateExecutor(
        string workflowId,
        DeclarativeWorkflowOptions options,
        Func<TInput, ChatMessage>? inputTransform = null)
    {
        inputTransform ??= (input) => DeclarativeWorkflowBuilder.DefaultTransform(input);
        WorkflowScopes scopes = new();
        scopes.InitializeSystem();
        //scopes.Initialize(workflowElement.WrapWithBot(), options.Configuration); // %%% NEED SOMETHING ELSE
        DeclarativeWorkflowState state = new(options.CreateRecalcEngine(), scopes); // %%% REMOVE
        return new DeclarativeWorkflowExecutor<TInput>(workflowId, state, inputTransform, isEjected: true); // %%% TODO
    }
}

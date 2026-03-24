// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Yaml;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Builder for converting a Foundry workflow object-model YAML definition into a process.
/// </summary>
public static class DeclarativeWorkflowBuilder
{
    /// <summary>
    /// Transforms the input message into a <see cref="ChatMessage"/> based on <see cref="object.ToString()"/>.
    /// Also performs pass-through for <see cref="ChatMessage"/> input.
    /// </summary>
    /// <param name="message">The input message to transform.</param>
    /// <returns>The transformed message (as <see cref="ChatMessage"/></returns>
    public static ChatMessage DefaultTransform(object message) =>
            message switch
            {
                ChatMessage chatMessage => chatMessage,
                string stringMessage => new ChatMessage(ChatRole.User, stringMessage),
                _ => new(ChatRole.User, $"{message}")
            };

    /// <summary>
    /// Builder for converting a Foundry workflow object-model YAML definition into a process.
    /// </summary>
    /// <typeparam name="TInput">The type of the input message</typeparam>
    /// <param name="workflowFile">The path to the workflow.</param>
    /// <param name="options">Configuration options for workflow execution.</param>
    /// <param name="inputTransform">An optional function to transform the input message into a <see cref="ChatMessage"/>.</param>
    /// <returns></returns>
    public static Workflow Build<TInput>(
        string workflowFile,
        DeclarativeWorkflowOptions options,
        Func<TInput, ChatMessage>? inputTransform = null)
        where TInput : notnull
    {
        using StreamReader yamlReader = File.OpenText(workflowFile);
        return Build(yamlReader, options, inputTransform);
    }

    /// <summary>
    /// Builds a workflow from the provided YAML definition.
    /// </summary>
    /// <typeparam name="TInput">The type of the input message</typeparam>
    /// <param name="yamlReader">The reader that provides the workflow object model YAML.</param>
    /// <param name="options">Configuration options for workflow execution.</param>
    /// <param name="inputTransform">An optional function to transform the input message into a <see cref="ChatMessage"/>.</param>
    /// <returns>The <see cref="Workflow"/> that corresponds with the YAML object model.</returns>
    public static Workflow Build<TInput>(
        TextReader yamlReader,
        DeclarativeWorkflowOptions options,
        Func<TInput, ChatMessage>? inputTransform = null)
        where TInput : notnull
    {
        AdaptiveDialog workflowElement = ReadWorkflow(yamlReader);
        string rootId = WorkflowActionVisitor.Steps.Root(workflowElement);

        WorkflowFormulaState state = new(options.CreateRecalcEngine());
        state.Initialize(workflowElement.WrapWithBot(), options.Configuration);
        DeclarativeWorkflowExecutor<TInput> rootExecutor =
            new(rootId,
                options,
                state,
                message => inputTransform?.Invoke(message) ?? DefaultTransform(message));

        WorkflowActionVisitor visitor = new(rootExecutor, state, options);
        WorkflowElementWalker walker = new(visitor);
        walker.Visit(workflowElement);

        return visitor.Complete();
    }

    private static AdaptiveDialog ReadWorkflow(TextReader yamlReader)
    {
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new DeclarativeModelException("Workflow undefined.");

        // "Workflow" is an alias for "AdaptiveDialog"
        if (rootElement is not AdaptiveDialog workflowElement)
        {
            throw new DeclarativeModelException($"Unsupported root element: {rootElement.GetType().Name}. Expected an {nameof(Workflow)}.");
        }

        return workflowElement;
    }
}

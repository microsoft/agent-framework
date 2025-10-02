// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Yaml;
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

    /// <summary>
    /// Generates source code (provider/executor scaffolding) for the workflow defined in the YAML file.
    /// </summary>
    /// <param name="workflowFile">The path to the workflow YAML file.</param>
    /// <param name="workflowLanguage">The language to use for the generated code.</param>
    /// <param name="workflowNamespace">Optional target namespace for the generated code.</param>
    /// <param name="workflowPrefix">Optional prefix for generated workflow type.</param>
    /// <returns>The generated source code representing the workflow.</returns>
    public static string Eject(
        string workflowFile,
        DeclarativeWorkflowLanguage workflowLanguage,
        string? workflowNamespace = null,
        string? workflowPrefix = null)
    {
        using StreamReader yamlReader = File.OpenText(workflowFile);
        return Eject(yamlReader, workflowLanguage, workflowNamespace, workflowPrefix);
    }

    /// <summary>
    /// Generates source code (provider/executor scaffolding) for the workflow defined in the provided YAML reader.
    /// </summary>
    /// <param name="yamlReader">The reader supplying the workflow YAML.</param>
    /// <param name="workflowLanguage">The language to use for the generated code.</param>
    /// <param name="workflowNamespace">Optional target namespace for the generated code.</param>
    /// <param name="workflowPrefix">Optional prefix for generated workflow type.</param>
    /// <returns>The generated source code representing the workflow.</returns>
    public static string Eject(
        TextReader yamlReader,
        DeclarativeWorkflowLanguage workflowLanguage,
        string? workflowNamespace = null,
        string? workflowPrefix = null)
    {
        if (workflowLanguage != DeclarativeWorkflowLanguage.CSharp)
        {
            throw new NotSupportedException($"Converting workflow to {workflowLanguage} is not currently supported.");
        }

        AdaptiveDialog workflowElement = ReadWorkflow(yamlReader);

        string rootId = WorkflowActionVisitor.Steps.Root(workflowElement);
        WorkflowTypeInfo typeInfo = workflowElement.WrapWithBot().Describe();

        WorkflowTemplateVisitor visitor = new(rootId, typeInfo);
        WorkflowElementWalker walker = new(visitor);
        walker.Visit(workflowElement);

        return visitor.Complete(workflowNamespace, workflowPrefix);
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

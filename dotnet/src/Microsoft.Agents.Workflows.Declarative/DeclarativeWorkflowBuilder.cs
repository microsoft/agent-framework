// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Yaml;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Builder for converting a Foundry workflow object-model YAML definition into a process.
/// </summary>
public static class DeclarativeWorkflowBuilder
{
    /// <summary>
    /// Builds a process from the provided YAML definition of a CPS Topic ObjectModel.
    /// </summary>
    /// <typeparam name="TInput">The type of the input message</typeparam>
    /// <param name="workflowFile">The path to the workflow.</param>
    /// <param name="options">Configuration options for workflow execution.</param>
    /// <param name="inputTransform">An optional function to transform the input message into a <see cref="ChatMessage"/>.</param>
    /// <returns></returns>
    public static Workflow<TInput> Build<TInput>(
        string workflowFile,
        DeclarativeWorkflowOptions options,
        Func<TInput, ChatMessage>? inputTransform = null)
        where TInput : notnull
    {
        using StreamReader yamlReader = File.OpenText(workflowFile);
        return Build(yamlReader, options, inputTransform);
    }

    /// <summary>
    /// Builds a process from the provided YAML definition of a CPS Topic ObjectModel.
    /// </summary>
    /// <typeparam name="TInput">The type of the input message</typeparam>
    /// <param name="yamlReader">The reader that provides the workflow object model YAML.</param>
    /// <param name="options">Configuration options for workflow execution.</param>
    /// <param name="inputTransform">An optional function to transform the input message into a <see cref="ChatMessage"/>.</param>
    /// <returns>The <see cref="Workflow"/> that corresponds with the YAML object model.</returns>
    public static Workflow<TInput> Build<TInput>(
        TextReader yamlReader,
        DeclarativeWorkflowOptions options,
        Func<TInput, ChatMessage>? inputTransform = null)
        where TInput : notnull
    {
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new DeclarativeModelException("Workflow undefined.");

        // ISSUE #486 - Use "Workflow" element for Foundry.
        if (rootElement is not AdaptiveDialog workflowElement)
        {
            throw new DeclarativeModelException($"Unsupported root element: {rootElement.GetType().Name}. Expected an {nameof(AdaptiveDialog)}.");
        }

        string rootId = WorkflowActionVisitor.Steps.Root(workflowElement.BeginDialog?.Id.Value);

        WorkflowFormulaState state = new(options.CreateRecalcEngine());
        state.Initialize(workflowElement.WrapWithBot(), options.Configuration);
        DeclarativeWorkflowExecutor<TInput> rootExecutor =
            new(rootId,
                state,
                message => inputTransform?.Invoke(message) ?? DefaultTransform(message));

        WorkflowActionVisitor visitor = new(rootExecutor, state, options);
        WorkflowElementWalker walker = new(visitor);
        walker.Visit(rootElement);

        return visitor.Complete<TInput>();
    }

    /// <summary>
    /// Generates source code (provider/executor scaffolding) for the workflow defined in the YAML file.
    /// </summary>
    /// <param name="workflowFile">The path to the workflow YAML file.</param>
    /// <param name="workflowNamespace">Optional target namespace for the generated code.</param>
    /// <param name="workflowPrefix">Optional prefix for generated workflow type.</param>
    /// <returns>The generated source code representing the workflow.</returns>
    public static string Eject(
        string workflowFile,
        string? workflowNamespace = null,
        string? workflowPrefix = null)
    {
        using StreamReader yamlReader = File.OpenText(workflowFile);
        return Eject(yamlReader, workflowNamespace, workflowPrefix);
    }

    /// <summary>
    /// Generates source code (provider/executor scaffolding) for the workflow defined in the provided YAML reader.
    /// </summary>
    /// <param name="yamlReader">The reader supplying the workflow YAML.</param>
    /// <param name="workflowNamespace">Optional target namespace for the generated code.</param>
    /// <param name="workflowPrefix">Optional prefix for generated workflow type.</param>
    /// <returns>The generated source code representing the workflow.</returns>
    public static string Eject(
        TextReader yamlReader,
        string? workflowNamespace = null,
        string? workflowPrefix = null)
    {
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new DeclarativeModelException("Workflow undefined.");

        // ISSUE #486 - Use "Workflow" element for Foundry.
        if (rootElement is not AdaptiveDialog workflowElement)
        {
            throw new DeclarativeModelException($"Unsupported root element: {rootElement.GetType().Name}. Expected an {nameof(AdaptiveDialog)}.");
        }

        string rootId = WorkflowActionVisitor.Steps.Root(workflowElement.BeginDialog?.Id.Value);

        WorkflowTypeInfo typeInfo = workflowElement.WrapWithBot().Describe();

        WorkflowEjectVisitor visitor = new(rootId, typeInfo);
        WorkflowElementWalker walker = new(visitor);
        walker.Visit(rootElement);

        ProviderTemplate template =
            new(rootId, visitor.Executors, visitor.Instances, visitor.Edges)
            {
                Namespace = workflowNamespace,
                Prefix = workflowPrefix,
            };

        return template.TransformText();
    }

    private static ChatMessage DefaultTransform(object message) =>
            message switch
            {
                ChatMessage chatMessage => chatMessage,
                string stringMessage => new ChatMessage(ChatRole.User, stringMessage),
                _ => new(ChatRole.User, $"{message}")
            };
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
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
    /// <param name="options">The execution context for the workflow.</param>
    /// <param name="inputTransform">An optional function to transform the input message into a <see cref="ChatMessage"/>.</param>
    /// <returns></returns>
    public static Workflow<TInput> Build<TInput>(
        string workflowFile,
        DeclarativeWorkflowOptions options,
        Func<TInput, ChatMessage>? inputTransform = null)
        where TInput : notnull
    {
        using StreamReader yamlReader = File.OpenText(workflowFile);
        return Build<TInput>(yamlReader, options, inputTransform);
    }
    /// <summary>
    /// Builds a process from the provided YAML definition of a CPS Topic ObjectModel.
    /// </summary>
    /// <typeparam name="TInput">The type of the input message</typeparam>
    /// <param name="yamlReader">The reader that provides the workflow object model YAML.</param>
    /// <param name="options">The execution context for the workflow.</param>
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

        string rootId = WorkflowActionVisitor.RootId(workflowElement.BeginDialog?.Id.Value ?? "workflow");

        WorkflowScopes scopes = new();
        scopes.Initialize(WrapWithBot(workflowElement), options.Configuration);
        DeclarativeWorkflowState state = new(options.CreateRecalcEngine(), scopes);
        DeclarativeWorkflowExecutor<TInput> rootExecutor =
            new(rootId,
                state,
                message => inputTransform?.Invoke(message) ?? DefaultTransform(message));

        WorkflowActionVisitor visitor = new(rootExecutor, state, options);
        WorkflowElementWalker walker = new(rootElement, visitor);

        return walker.GetWorkflow<TInput>();
    }

    private static ChatMessage DefaultTransform(object message) =>
            message switch
            {
                ChatMessage chatMessage => chatMessage,
                string stringMessage => new ChatMessage(ChatRole.User, stringMessage),
                _ => new(ChatRole.User, $"{message}")
            };

    // Wrap with bot to ensure schema is set.
    private static AdaptiveDialog WrapWithBot(AdaptiveDialog dialog)
    {
        BotDefinition bot
            = new BotDefinition.Builder
            {
                Components =
                    {
                        new DialogComponent.Builder
                        {
                            SchemaName = dialog.HasSchemaName ? dialog.SchemaName : "default-schema",
                            Dialog = new AdaptiveDialog.Builder(dialog),
                        }
                    }
            }.Build();

        return bot.Descendants().OfType<AdaptiveDialog>().First();
    }
}

// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Yaml;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Builder for converting a Foundry workflow object-model YAML definition into a process.
/// </summary>
public static class DeclarativeWorkflowBuilder
{
    /// <summary>
    /// Builds a process from the provided YAML definition of a CPS Topic ObjectModel.
    /// </summary>
    /// <param name="yamlReader">The reader that provides the workflow object model YAML.</param>
    /// <param name="context">The execution context for the workflow.</param>
    /// <returns>The <see cref="Workflow"/> that corresponds with the YAML object model.</returns>
    public static Workflow<TInput> Build<TInput>(TextReader yamlReader, DeclarativeWorkflowOptions context) where TInput : notnull
    {
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new UnknownActionException("Unable to parse workflow.");
        string rootId = WorkflowActionVisitor.RootId(GetWorkflowId(rootElement));

        DeclarativeWorkflowExecutor<TInput> rootExecutor = new(rootId);

        WorkflowActionVisitor visitor = new(rootExecutor, context);
        WorkflowElementWalker walker = new(rootElement, visitor);

        return walker.GetWorkflow<TInput>();
    }

    private static string? GetWorkflowId(BotElement element) => // %%% CPS - WORKFLOW TYPE
        element switch
        {
            AdaptiveDialog adaptiveDialog => adaptiveDialog.BeginDialog?.Id.Value,
            DialogAction actionDialog => actionDialog.Id.Value,
            _ => throw new UnknownActionException($"Unsupported root element: {element.GetType().Name}."),
        };
}

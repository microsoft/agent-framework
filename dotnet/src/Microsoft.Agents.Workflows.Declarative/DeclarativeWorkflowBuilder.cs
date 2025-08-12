// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative.Execution;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
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
    /// <param name="context">The hosting context for the workflow.</param>
    /// <returns>The <see cref="Workflow"/> that corresponds with the YAML object model.</returns>
    public static Workflow<string> Build(TextReader yamlReader, DeclarativeWorkflowContext? context = null)
    {
        Console.WriteLine("@ PARSING YAML");
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new UnknownActionException("Unable to parse workflow.");
        string rootId = $"root_{GetRootId(rootElement)}";

        Console.WriteLine("@ INITIALIZING BUILDER");
        context ??= DeclarativeWorkflowContext.Default;
        WorkflowScopes scopes = new();
        DeclarativeWorkflowExecutor rootExecutor = new(scopes, rootId);

        Console.WriteLine("@ INTERPRETING WORKFLOW");
        WorkflowActionVisitor visitor = new(rootExecutor, context, scopes);
        WorkflowElementWalker walker = new(rootElement, visitor);

        return walker.Workflow;
    }

    private static string GetRootId(BotElement element) => // %%% WORKFLOW TYPE
        element switch
        {
            AdaptiveDialog adaptiveDialog => adaptiveDialog.BeginDialog?.Id.Value ?? throw new UnknownActionException("Undefined dialog"),
            _ => throw new UnknownActionException($"Unsupported root element: {element.GetType().Name}."),
        };
}

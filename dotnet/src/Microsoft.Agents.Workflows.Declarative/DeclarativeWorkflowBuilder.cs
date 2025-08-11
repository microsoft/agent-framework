// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using Microsoft.Agents.Workflows.Core;
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
    /// <param name="messageId">The identifier for the message.</param>
    /// <param name="context">The hosting context for the workflow.</param>
    /// <returns>The <see cref="Workflow"/> that corresponds with the YAML object model.</returns>
    public static Workflow<string> Build(TextReader yamlReader, string messageId, WorkflowContext? context = null)
    {
        Console.WriteLine("@ PARSING YAML");
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new InvalidOperationException("Unable to parse YAML content."); // %%% EXCEPTION TYPE
        string rootId = $"root_{GetRootId(rootElement)}";

        Console.WriteLine("@ INITIALIZING BUILDER");
        ProcessActionScopes scopes = new();
        DeclarativeWorkflowExecutor rootExecutor = new(scopes, rootId);

        Console.WriteLine("@ INTERPRETING WORKFLOW");
        ProcessActionVisitor visitor = new(rootExecutor, context ?? new WorkflowContext(), scopes); // %%% DEFAULT CONTEXT (IMMUTABLE)
        ProcessActionWalker walker = new(rootElement, visitor);

        Console.WriteLine("@ FINALIZING WORKFLOW");
        //ProcessStepBuilder errorHandler = // %%% DYNAMIC/CONTEXT ???
        //    processBuilder.AddStepFromFunction(
        //        $"{processBuilder.Name}_unhandled_error",
        //        (kernel, context) =>
        //        {
        //            // Handle unhandled errors here
        //            Console.WriteLine("*** PROCESS ERROR - Unhandled error"); // %%% EXTERNAL
        //            return Task.CompletedTask;
        //        });
        //processBuilder.OnError().SendEventTo(new ProcessFunctionTargetBuilder(errorHandler));

        return walker.Workflow;
    }

    private static string GetRootId(BotElement element) =>
        element switch
        {
            AdaptiveDialog adaptiveDialog => adaptiveDialog.BeginDialog?.Id.Value ?? throw new InvalidOperationException("Undefined dialog"), // %%% EXCEPTION TYPE / WORKFLOW TYPE
            _ => throw new InvalidOperationException($"Unsupported root element: {element.GetType().Name}."), // %%% EXCEPTION TYPE
        };
}

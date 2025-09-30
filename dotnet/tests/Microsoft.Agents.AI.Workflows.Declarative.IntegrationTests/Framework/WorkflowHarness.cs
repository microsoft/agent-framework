// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Shared.Code;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

internal static class WorkflowHarness
{
    public static async Task<WorkflowEvents> RunAsync<TInput>(Workflow workflow, TInput input) where TInput : notnull
    {
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, input);
        IReadOnlyList<WorkflowEvent> workflowEvents = run.WatchStreamAsync().ToEnumerable().ToList();
        return new WorkflowEvents(workflowEvents);
    }

    public static async Task<WorkflowEvents> RunCodeAsync<TInput>(
        string workflowProviderCode,
        string workflowProviderName,
        string workflowProviderNamespace,
        DeclarativeWorkflowOptions options,
        TInput input) where TInput : notnull
    {
        // Compile the code
        Assembly assembly = Compiler.Build(workflowProviderCode, Compiler.RepoDependencies(typeof(DeclarativeWorkflowBuilder)));
        Type? type = assembly.GetType($"{workflowProviderNamespace}.{workflowProviderName}");
        Assert.NotNull(type);
        MethodInfo? method = type.GetMethod("CreateWorkflow");
        Assert.NotNull(method);
        MethodInfo genericMethod = method.MakeGenericMethod(typeof(TInput));
        object? workflowObject = genericMethod.Invoke(null, [options, null]);
        Workflow workflow = Assert.IsType<Workflow>(workflowObject);

        Console.WriteLine("RUNNING WORKFLOW...");
        return await RunAsync(workflow, input);
    }
}

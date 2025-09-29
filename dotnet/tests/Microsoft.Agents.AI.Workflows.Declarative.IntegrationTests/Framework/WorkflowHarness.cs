// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Emit;
using Microsoft.Extensions.AI;
using Xunit.Sdk;

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
        SyntaxTree syntaxTree = CSharpSyntaxTree.ParseText(workflowProviderCode);
        CSharpCompilation compilation = CSharpCompilation.Create(
            "DynamicAssembly",
            [syntaxTree],
            [
                MetadataReference.CreateFromFile(typeof(object).Assembly.Location),
                MetadataReference.CreateFromFile(typeof(Console).Assembly.Location),
                MetadataReference.CreateFromFile(typeof(Enumerable).Assembly.Location),
#if NET
                MetadataReference.CreateFromFile(Assembly.Load("System.Runtime").Location),
#else
                MetadataReference.CreateFromFile(typeof(ValueTask).Assembly.Location),
#endif
                MetadataReference.CreateFromFile(typeof(AsyncEnumerable).Assembly.Location),
                MetadataReference.CreateFromFile(typeof(ChatMessage).Assembly.Location),
                MetadataReference.CreateFromFile(typeof(AIAgent).Assembly.Location),
                MetadataReference.CreateFromFile(typeof(Workflow).Assembly.Location),
                MetadataReference.CreateFromFile(typeof(DeclarativeWorkflowBuilder).Assembly.Location),
            ],
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary)
        );

        using MemoryStream memoryStream = new();
        EmitResult result = compilation.Emit(memoryStream);

        if (!result.Success)
        {
            Console.WriteLine("COMPLILATION FAILURE:");
            foreach (var diagnostic in result.Diagnostics)
            {
                Console.WriteLine(diagnostic.ToString());
            }
            throw new XunitException("Compilation failed.");
        }

        Console.WriteLine("COMPLILATION SUCCEEDED...");
        memoryStream.Seek(0, SeekOrigin.Begin);
        Assembly assembly = Assembly.Load(memoryStream.ToArray());
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

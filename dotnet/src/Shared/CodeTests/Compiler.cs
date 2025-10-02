// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
#if !NET
using System.Threading.Tasks;
#endif
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.Emit;
using Microsoft.Extensions.AI;
using Xunit.Sdk;

namespace Shared.Code;

internal static class Compiler
{
    public static IEnumerable<Assembly> RepoDependencies(params IEnumerable<Type> types)
    {
        yield return typeof(object).Assembly;
        yield return typeof(Console).Assembly;
        yield return typeof(Enumerable).Assembly;
#if NET
        yield return Assembly.Load("System.Runtime");
#else
        yield return Assembly.LoadFrom(AppDomain.CurrentDomain.GetAssemblies().Single(a => a.GetName().Name == "netstandard").Location);
        yield return typeof(IAsyncEnumerable<>).Assembly;
        yield return typeof(ValueTask).Assembly;
#endif
        yield return typeof(ChatMessage).Assembly;
        yield return typeof(AIAgent).Assembly;
        yield return typeof(Workflow).Assembly;

        foreach (Type type in types)
        {
            yield return type.Assembly;
        }
    }

    public static Assembly Build(string workflowProviderCode, params IEnumerable<Assembly> dependencies)
    {
        // Compile the code
        SyntaxTree syntaxTree = CSharpSyntaxTree.ParseText(workflowProviderCode);
        CSharpCompilation compilation = CSharpCompilation.Create(
            "DynamicAssembly",
            [syntaxTree],
            dependencies.Select(d => MetadataReference.CreateFromFile(d.Location)),
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
        return Assembly.Load(memoryStream.ToArray());
    }
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace Microsoft.Agents.AI.Workflows.Generators.UnitTests;

/// <summary>
/// Helper class for testing the ExecutorRouteGenerator.
/// </summary>
public static class GeneratorTestHelper
{
    /// <summary>
    /// Runs the ExecutorRouteGenerator on the provided source code and returns the result.
    /// </summary>
    public static GeneratorRunResult RunGenerator(string source) => RunGenerator([source]);

    /// <summary>
    /// Runs the ExecutorRouteGenerator on multiple source files and returns the result.
    /// Use this to test scenarios with partial classes split across files.
    /// </summary>
    public static GeneratorRunResult RunGenerator(params string[] sources)
    {
        var syntaxTrees = sources.Select(s => CSharpSyntaxTree.ParseText(s)).ToArray();

        var references = GetMetadataReferences();

        var compilation = CSharpCompilation.Create(
            assemblyName: "TestAssembly",
            syntaxTrees: syntaxTrees,
            references: references,
            options: new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

        var generator = new ExecutorRouteGenerator();

        GeneratorDriver driver = CSharpGeneratorDriver.Create(generator);
        driver = driver.RunGeneratorsAndUpdateCompilation(compilation, out var outputCompilation, out var diagnostics);

        var runResult = driver.GetRunResult();

        return new GeneratorRunResult(
            runResult,
            outputCompilation,
            diagnostics);
    }

    /// <summary>
    /// Runs the generator and asserts that it produces exactly one generated file with the expected content.
    /// </summary>
    public static void AssertGeneratesSource(string source, string expectedGeneratedSource)
    {
        var result = RunGenerator(source);

        result.RunResult.GeneratedTrees.Should().HaveCount(1, "expected exactly one generated file");

        var generatedSource = result.RunResult.GeneratedTrees[0].ToString();
        generatedSource.Should().Contain(expectedGeneratedSource);
    }

    /// <summary>
    /// Runs the generator and asserts that no source is generated.
    /// </summary>
    public static void AssertGeneratesNoSource(string source)
    {
        var result = RunGenerator(source);
        result.RunResult.GeneratedTrees.Should().BeEmpty("expected no generated files");
    }

    /// <summary>
    /// Runs the generator and asserts that a specific diagnostic is produced.
    /// </summary>
    public static void AssertProducesDiagnostic(string source, string diagnosticId)
    {
        var result = RunGenerator(source);

        var generatorDiagnostics = result.RunResult.Diagnostics;
        generatorDiagnostics.Should().Contain(d => d.Id == diagnosticId,
            $"expected diagnostic {diagnosticId} to be produced");
    }

    /// <summary>
    /// Runs the generator and asserts that compilation succeeds with no errors.
    /// </summary>
    public static void AssertCompilationSucceeds(string source)
    {
        var result = RunGenerator(source);

        var errors = result.OutputCompilation.GetDiagnostics()
            .Where(d => d.Severity == DiagnosticSeverity.Error)
            .ToList();

        errors.Should().BeEmpty("compilation should succeed without errors");
    }

    private static ImmutableArray<MetadataReference> GetMetadataReferences()
    {
        var assemblies = new[]
        {
            typeof(object).Assembly, // System.Runtime
            typeof(Attribute).Assembly, // System.Runtime
            typeof(ValueTask).Assembly, // System.Threading.Tasks.Extensions
            typeof(CancellationToken).Assembly, // System.Threading
            typeof(ISet<>).Assembly, // System.Collections
            typeof(Executor).Assembly, // Microsoft.Agents.AI.Workflows
        };

        var references = new List<MetadataReference>();

        foreach (var assembly in assemblies)
        {
            references.Add(MetadataReference.CreateFromFile(assembly.Location));
        }

        // Add netstandard reference
        var netstandardAssembly = Assembly.Load("netstandard, Version=2.0.0.0");
        references.Add(MetadataReference.CreateFromFile(netstandardAssembly.Location));

        // Add System.Runtime reference for core types
        var runtimeAssemblyPath = Path.GetDirectoryName(typeof(object).Assembly.Location)!;
        var systemRuntimePath = Path.Combine(runtimeAssemblyPath, "System.Runtime.dll");
        if (File.Exists(systemRuntimePath))
        {
            references.Add(MetadataReference.CreateFromFile(systemRuntimePath));
        }

        return [.. references.Distinct()];
    }
}

/// <summary>
/// Contains the results of running the generator.
/// </summary>
public record GeneratorRunResult(
    GeneratorDriverRunResult RunResult,
    Compilation OutputCompilation,
    ImmutableArray<Diagnostic> Diagnostics);

// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text;
using Microsoft.Agents.AI.Workflows.Generators.Analysis;
using Microsoft.Agents.AI.Workflows.Generators.Generation;
using Microsoft.Agents.AI.Workflows.Generators.Models;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;

namespace Microsoft.Agents.AI.Workflows.Generators;

/// <summary>
/// Roslyn incremental source generator that generates ConfigureRoutes implementations
/// for executor classes with [MessageHandler] attributed methods, and/or ConfigureSentTypes/ConfigureYieldTypes
/// overrides for classes with [SendsMessage]/[YieldsOutput] attributes.
/// </summary>
[Generator]
public sealed class ExecutorRouteGenerator : IIncrementalGenerator
{
    private const string MessageHandlerAttributeFullName = "Microsoft.Agents.AI.Workflows.MessageHandlerAttribute";
    private const string SendsMessageAttributeFullName = "Microsoft.Agents.AI.Workflows.SendsMessageAttribute";
    private const string YieldsOutputAttributeFullName = "Microsoft.Agents.AI.Workflows.YieldsOutputAttribute";

    /// <inheritdoc/>
    public void Initialize(IncrementalGeneratorInitializationContext context)
    {
        // Pipeline 1: Methods with [MessageHandler] attribute
        IncrementalValuesProvider<MethodAnalysisResult> methodAnalysisResults = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                fullyQualifiedMetadataName: MessageHandlerAttributeFullName,
                predicate: static (node, _) => node is MethodDeclarationSyntax,
                transform: static (ctx, ct) => SemanticAnalyzer.AnalyzeHandlerMethod(ctx, ct))
            .Where(static result => !string.IsNullOrWhiteSpace(result.ClassKey));

        // Pipeline 2: Classes with [SendsMessage] attribute
        IncrementalValuesProvider<ClassProtocolInfo> sendProtocolResults = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                fullyQualifiedMetadataName: SendsMessageAttributeFullName,
                predicate: static (node, _) => node is ClassDeclarationSyntax,
                transform: static (ctx, ct) => SemanticAnalyzer.AnalyzeClassProtocolAttribute(ctx, ProtocolAttributeKind.Send, ct))
            .SelectMany(static (results, _) => results);

        // Pipeline 3: Classes with [YieldsOutput] attribute
        IncrementalValuesProvider<ClassProtocolInfo> yieldProtocolResults = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                fullyQualifiedMetadataName: YieldsOutputAttributeFullName,
                predicate: static (node, _) => node is ClassDeclarationSyntax,
                transform: static (ctx, ct) => SemanticAnalyzer.AnalyzeClassProtocolAttribute(ctx, ProtocolAttributeKind.Yield, ct))
            .SelectMany(static (results, _) => results);

        // Combine all protocol results (Send + Yield)
        IncrementalValuesProvider<ClassProtocolInfo> allProtocolResults = sendProtocolResults
            .Collect()
            .Combine(yieldProtocolResults.Collect())
            .SelectMany(static (tuple, _) => tuple.Left.AddRange(tuple.Right));

        // Combine all pipelines and produce AnalysisResults grouped by class
        IncrementalValuesProvider<AnalysisResult> combinedResults = methodAnalysisResults
            .Collect()
            .Combine(allProtocolResults.Collect())
            .SelectMany(static (tuple, _) => CombineAllResults(tuple.Left, tuple.Right));

        // Generate source for valid executors
        context.RegisterSourceOutput(
            combinedResults.Where(static r => r.ExecutorInfo is not null),
            static (ctx, result) =>
            {
                string source = SourceBuilder.Generate(result.ExecutorInfo!);
                string hintName = GetHintName(result.ExecutorInfo!);
                ctx.AddSource(hintName, SourceText.From(source, Encoding.UTF8));
            });

        // Report diagnostics
        context.RegisterSourceOutput(
            combinedResults.Where(static r => !r.Diagnostics.IsEmpty),
            static (ctx, result) =>
            {
                foreach (Diagnostic diagnostic in result.Diagnostics)
                {
                    ctx.ReportDiagnostic(diagnostic);
                }
            });
    }

    /// <summary>
    /// Combines method analysis results with class protocol results, grouping by class key.
    /// Classes with [MessageHandler] methods get full generation; classes with only protocol
    /// attributes get protocol-only generation.
    /// </summary>
    private static IEnumerable<AnalysisResult> CombineAllResults(
        ImmutableArray<MethodAnalysisResult> methodResults,
        ImmutableArray<ClassProtocolInfo> protocolResults)
    {
        // Group method results by class
        Dictionary<string, List<MethodAnalysisResult>> methodsByClass = methodResults
            .GroupBy(r => r.ClassKey)
            .ToDictionary(g => g.Key, g => g.ToList());

        // Group protocol results by class
        Dictionary<string, List<ClassProtocolInfo>> protocolsByClass = protocolResults
            .GroupBy(r => r.ClassKey)
            .ToDictionary(g => g.Key, g => g.ToList());

        // Track which classes we've processed
        HashSet<string> processedClasses = new();

        // Process classes that have [MessageHandler] methods
        foreach (KeyValuePair<string, List<MethodAnalysisResult>> kvp in methodsByClass)
        {
            processedClasses.Add(kvp.Key);
            yield return SemanticAnalyzer.CombineHandlerMethodResults(kvp.Value);
        }

        // Process classes that only have protocol attributes (no [MessageHandler] methods)
        foreach (KeyValuePair<string, List<ClassProtocolInfo>> kvp in protocolsByClass)
        {
            if (!processedClasses.Contains(kvp.Key))
            {
                yield return SemanticAnalyzer.CombineOutputOnlyResults(kvp.Value);
            }
        }
    }

    /// <summary>
    /// Generates a hint (virtual file) name for the generated source file based on the ExecutorInfo.
    /// </summary>
    private static string GetHintName(ExecutorInfo info)
    {
        var sb = new StringBuilder();

        if (!string.IsNullOrWhiteSpace(info.Namespace))
        {
            sb.Append(info.Namespace)
               .Append('.');
        }

        if (info.IsNested)
        {
            sb.Append(info.ContainingTypeChain)
              .Append('.');
        }

        sb.Append(info.ClassName);

        // Handle generic type parameters in hint name
        if (!string.IsNullOrWhiteSpace(info.GenericParameters))
        {
            // Replace < > with underscores for valid file name
            sb.Append('_')
              .Append(info.GenericParameters!.Length - 2); // Number of type params approximation
        }

        sb.Append(".g.cs");

        return sb.ToString();
    }
}

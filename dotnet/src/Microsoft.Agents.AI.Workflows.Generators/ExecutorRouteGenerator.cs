// Copyright (c) Microsoft. All rights reserved.

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
/// for executor classes with [MessageHandler] attributed methods.
/// </summary>
[Generator]
public sealed class ExecutorRouteGenerator : IIncrementalGenerator
{
    private const string MessageHandlerAttributeFullName = "Microsoft.Agents.AI.Workflows.MessageHandlerAttribute";

    /// <inheritdoc/>
    public void Initialize(IncrementalGeneratorInitializationContext context)
    {
        // Step 1: Use ForAttributeWithMetadataName to efficiently find methods with [MessageHandler] attribute. For each method found, build a MethodAnalysisResult.
        var methodAnalysisResults = context.SyntaxProvider
            .ForAttributeWithMetadataName(
                fullyQualifiedMetadataName: MessageHandlerAttributeFullName,
                predicate: static (node, _) => node is MethodDeclarationSyntax,
                transform: static (ctx, ct) => SemanticAnalyzer.AnalyzeMethod(ctx, ct))
            .Where(static result => !string.IsNullOrEmpty(result.ClassKey));

        // Step 2: Collect all MethodAnalysisResults, group by class, and then combine into a single AnalysisResult per class.
        var groupedByClass = methodAnalysisResults
            .Collect()
            .SelectMany(static (results, _) =>
            {
                // Group by class key and combine into AnalysisResult
                return results
                    .GroupBy(r => r.ClassKey)
                    .Select(group => SemanticAnalyzer.CombineMethodResults(group));
            });

        // Step 3: Generate source for valid executors using the associated AnalysisResult.
        context.RegisterSourceOutput(
            groupedByClass.Where(static r => r.ExecutorInfo is not null),
            static (ctx, result) =>
            {
                string source = SourceBuilder.Generate(result.ExecutorInfo!);
                string hintName = GetHintName(result.ExecutorInfo!);
                ctx.AddSource(hintName, SourceText.From(source, Encoding.UTF8));
            });

        // Step 4: Report diagnostics
        context.RegisterSourceOutput(
            groupedByClass.Where(static r => !r.Diagnostics.IsEmpty),
            static (ctx, result) =>
            {
                foreach (var diagnostic in result.Diagnostics)
                {
                    ctx.ReportDiagnostic(diagnostic);
                }
            });
    }

    /// <summary>
    /// Generates a hint (virtual file) name for the generated source file based on the ExecutorInfo.
    /// </summary>
    private static string GetHintName(ExecutorInfo info)
    {
        var sb = new StringBuilder();

        if (!string.IsNullOrEmpty(info.Namespace))
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
        if (!string.IsNullOrEmpty(info.GenericParameters))
        {
            // Replace < > with underscores for valid file name
            sb.Append('_')
              .Append(info.GenericParameters!.Length - 2); // Number of type params approximation
        }

        sb.Append(".g.cs");

        return sb.ToString();
    }
}

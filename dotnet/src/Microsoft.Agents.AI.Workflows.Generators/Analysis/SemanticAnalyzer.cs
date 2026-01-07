// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Threading;
using Microsoft.Agents.AI.Workflows.Generators.Diagnostics;
using Microsoft.Agents.AI.Workflows.Generators.Models;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace Microsoft.Agents.AI.Workflows.Generators.Analysis;

/// <summary>
/// Provides semantic analysis of executor route candidates.
/// </summary>
internal static class SemanticAnalyzer
{
    private const string ExecutorTypeName = "Microsoft.Agents.AI.Workflows.Executor";
    private const string WorkflowContextTypeName = "Microsoft.Agents.AI.Workflows.IWorkflowContext";
    private const string CancellationTokenTypeName = "System.Threading.CancellationToken";
    private const string ValueTaskTypeName = "System.Threading.Tasks.ValueTask";
    private const string MessageHandlerAttributeName = "Microsoft.Agents.AI.Workflows.MessageHandlerAttribute";
    private const string SendsMessageAttributeName = "Microsoft.Agents.AI.Workflows.SendsMessageAttribute";
    private const string YieldsMessageAttributeName = "Microsoft.Agents.AI.Workflows.YieldsMessageAttribute";

    /// <summary>
    /// Analyzes a method with [MessageHandler] attribute found by ForAttributeWithMetadataName.
    /// Returns a MethodAnalysisResult containing both method info and class context.
    /// </summary>
    public static MethodAnalysisResult AnalyzeMethod(
        GeneratorAttributeSyntaxContext context,
        CancellationToken cancellationToken)
    {
        var diagnostics = ImmutableArray.CreateBuilder<DiagnosticInfo>();

        // The target should be a method
        if (context.TargetSymbol is not IMethodSymbol methodSymbol)
        {
            return CreateEmptyResult();
        }

        // Get the containing class
        var classSymbol = methodSymbol.ContainingType;
        if (classSymbol is null)
        {
            return CreateEmptyResult();
        }

        // Get the method syntax for location info
        var methodSyntax = context.TargetNode as MethodDeclarationSyntax;

        // Extract class-level info
        var classKey = GetClassKey(classSymbol);
        var isPartialClass = IsPartialClass(classSymbol, cancellationToken);
        var derivesFromExecutor = DerivesFromExecutor(classSymbol);
        var hasManualConfigureRoutes = HasConfigureRoutesDefined(classSymbol);

        // Extract class metadata
        var @namespace = classSymbol.ContainingNamespace?.IsGlobalNamespace == true
            ? null
            : classSymbol.ContainingNamespace?.ToDisplayString();
        var className = classSymbol.Name;
        var genericParameters = GetGenericParameters(classSymbol);
        var isNested = classSymbol.ContainingType != null;
        var containingTypeChain = GetContainingTypeChain(classSymbol);
        var baseHasConfigureRoutes = BaseHasConfigureRoutes(classSymbol);
        var classSendTypes = GetClassLevelTypes(classSymbol, SendsMessageAttributeName);
        var classYieldTypes = GetClassLevelTypes(classSymbol, YieldsMessageAttributeName);

        // Validate class-level requirements and collect diagnostics
        if (!derivesFromExecutor)
        {
            diagnostics.Add(DiagnosticInfo.Create(
                "WFGEN004",
                methodSyntax?.Identifier.GetLocation() ?? context.TargetNode.GetLocation(),
                methodSymbol.Name,
                classSymbol.Name));

            return new MethodAnalysisResult(
                classKey, @namespace, className, genericParameters, isNested, containingTypeChain,
                baseHasConfigureRoutes, classSendTypes, classYieldTypes,
                isPartialClass, derivesFromExecutor, hasManualConfigureRoutes,
                Handler: null,
                Diagnostics: new EquatableArray<DiagnosticInfo>(diagnostics.ToImmutable()));
        }

        // Analyze the handler method
        var handler = AnalyzeHandler(methodSymbol, methodSyntax, diagnostics);

        return new MethodAnalysisResult(
            classKey, @namespace, className, genericParameters, isNested, containingTypeChain,
            baseHasConfigureRoutes, classSendTypes, classYieldTypes,
            isPartialClass, derivesFromExecutor, hasManualConfigureRoutes,
            handler,
            Diagnostics: new EquatableArray<DiagnosticInfo>(diagnostics.ToImmutable()));
    }

    /// <summary>
    /// Combines multiple MethodAnalysisResults for the same class into an AnalysisResult.
    /// </summary>
    public static AnalysisResult CombineMethodResults(IEnumerable<MethodAnalysisResult> methodResults)
    {
        var methods = methodResults.ToList();
        if (methods.Count == 0)
        {
            return AnalysisResult.Empty;
        }

        // All methods should have same class info - take from first
        var first = methods[0];

        // Combine all diagnostics
        var allDiagnostics = methods
            .SelectMany(m => m.Diagnostics)
            .ToImmutableArray();

        // Check class-level validation
        if (!first.DerivesFromExecutor)
        {
            // Diagnostics already added per-method
            return AnalysisResult.WithDiagnostics(
                allDiagnostics.Select(d => d.ToDiagnostic(null)).ToImmutableArray());
        }

        if (!first.IsPartialClass)
        {
            var diag = Diagnostic.Create(
                DiagnosticDescriptors.ClassMustBePartial,
                Location.None, // We don't have class location easily accessible here
                first.ClassName);
            return AnalysisResult.WithDiagnostics(
                allDiagnostics.Select(d => d.ToDiagnostic(null)).Append(diag).ToImmutableArray());
        }

        if (first.HasManualConfigureRoutes)
        {
            var diag = Diagnostic.Create(
                DiagnosticDescriptors.ConfigureRoutesAlreadyDefined,
                Location.None,
                first.ClassName);
            return AnalysisResult.WithDiagnostics(
                allDiagnostics.Select(d => d.ToDiagnostic(null)).Append(diag).ToImmutableArray());
        }

        // Collect valid handlers
        var handlers = methods
            .Where(m => m.Handler is not null)
            .Select(m => m.Handler!)
            .ToImmutableArray();

        if (handlers.Length == 0)
        {
            return AnalysisResult.WithDiagnostics(
                allDiagnostics.Select(d => d.ToDiagnostic(null)).ToImmutableArray());
        }

        var executorInfo = new ExecutorInfo(
            first.Namespace,
            first.ClassName,
            first.GenericParameters,
            first.IsNested,
            first.ContainingTypeChain,
            first.BaseHasConfigureRoutes,
            new EquatableArray<HandlerInfo>(handlers),
            first.ClassSendTypes,
            first.ClassYieldTypes);

        if (allDiagnostics.Length > 0)
        {
            return AnalysisResult.WithInfoAndDiagnostics(
                executorInfo,
                allDiagnostics.Select(d => d.ToDiagnostic(null)).ToImmutableArray());
        }

        return AnalysisResult.Success(executorInfo);
    }

    private static MethodAnalysisResult CreateEmptyResult()
    {
        return new MethodAnalysisResult(
            string.Empty, null, string.Empty, null, false, string.Empty,
            false, EquatableArray<string>.Empty, EquatableArray<string>.Empty,
            false, false, false,
            null, EquatableArray<DiagnosticInfo>.Empty);
    }

    private static string GetClassKey(INamedTypeSymbol classSymbol)
    {
        return classSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);
    }

    private static bool IsPartialClass(INamedTypeSymbol classSymbol, CancellationToken cancellationToken)
    {
        foreach (var syntaxRef in classSymbol.DeclaringSyntaxReferences)
        {
            var syntax = syntaxRef.GetSyntax(cancellationToken);
            if (syntax is ClassDeclarationSyntax classDecl &&
                classDecl.Modifiers.Any(SyntaxKind.PartialKeyword))
            {
                return true;
            }
        }

        return false;
    }

    private static bool DerivesFromExecutor(INamedTypeSymbol classSymbol)
    {
        var current = classSymbol.BaseType;
        while (current != null)
        {
            var fullName = current.OriginalDefinition.ToDisplayString();
            if (fullName == ExecutorTypeName || fullName.StartsWith(ExecutorTypeName + "<", StringComparison.Ordinal))
            {
                return true;
            }

            current = current.BaseType;
        }

        return false;
    }

    private static bool HasConfigureRoutesDefined(INamedTypeSymbol classSymbol)
    {
        foreach (var member in classSymbol.GetMembers("ConfigureRoutes"))
        {
            if (member is IMethodSymbol method && !method.IsAbstract &&
                SymbolEqualityComparer.Default.Equals(method.ContainingType, classSymbol))
            {
                return true;
            }
        }

        return false;
    }

    private static bool BaseHasConfigureRoutes(INamedTypeSymbol classSymbol)
    {
        var baseType = classSymbol.BaseType;
        while (baseType != null)
        {
            var fullName = baseType.OriginalDefinition.ToDisplayString();
            if (fullName == ExecutorTypeName)
            {
                return false;
            }

            foreach (var member in baseType.GetMembers("ConfigureRoutes"))
            {
                if (member is IMethodSymbol method && !method.IsAbstract)
                {
                    return true;
                }
            }

            baseType = baseType.BaseType;
        }

        return false;
    }

    private static HandlerInfo? AnalyzeHandler(
        IMethodSymbol methodSymbol,
        MethodDeclarationSyntax? methodSyntax,
        ImmutableArray<DiagnosticInfo>.Builder diagnostics)
    {
        var location = methodSyntax?.Identifier.GetLocation() ?? Location.None;

        // Check if static
        if (methodSymbol.IsStatic)
        {
            diagnostics.Add(DiagnosticInfo.Create("WFGEN007", location, methodSymbol.Name));
            return null;
        }

        // Check parameter count
        if (methodSymbol.Parameters.Length < 2)
        {
            diagnostics.Add(DiagnosticInfo.Create("WFGEN005", location, methodSymbol.Name));
            return null;
        }

        // Check second parameter is IWorkflowContext
        var secondParam = methodSymbol.Parameters[1];
        if (secondParam.Type.ToDisplayString() != WorkflowContextTypeName)
        {
            diagnostics.Add(DiagnosticInfo.Create("WFGEN001", location, methodSymbol.Name));
            return null;
        }

        // Check for optional CancellationToken as third parameter
        var hasCancellationToken = methodSymbol.Parameters.Length >= 3 &&
            methodSymbol.Parameters[2].Type.ToDisplayString() == CancellationTokenTypeName;

        // Analyze return type
        var returnType = methodSymbol.ReturnType;
        var signatureKind = GetSignatureKind(returnType);
        if (signatureKind == null)
        {
            diagnostics.Add(DiagnosticInfo.Create("WFGEN002", location, methodSymbol.Name));
            return null;
        }

        // Get input type
        var inputType = methodSymbol.Parameters[0].Type;
        var inputTypeName = inputType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);

        // Get output type
        string? outputTypeName = null;
        if (signatureKind == HandlerSignatureKind.ResultSync)
        {
            outputTypeName = returnType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);
        }
        else if (signatureKind == HandlerSignatureKind.ResultAsync && returnType is INamedTypeSymbol namedReturn)
        {
            if (namedReturn.TypeArguments.Length == 1)
            {
                outputTypeName = namedReturn.TypeArguments[0].ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);
            }
        }

        // Get Yield and Send types from attribute
        var (yieldTypes, sendTypes) = GetAttributeTypeArrays(methodSymbol);

        return new HandlerInfo(
            methodSymbol.Name,
            inputTypeName,
            outputTypeName,
            signatureKind.Value,
            hasCancellationToken,
            yieldTypes,
            sendTypes);
    }

    private static HandlerSignatureKind? GetSignatureKind(ITypeSymbol returnType)
    {
        var returnTypeName = returnType.ToDisplayString();

        if (returnType.SpecialType == SpecialType.System_Void)
        {
            return HandlerSignatureKind.VoidSync;
        }

        if (returnTypeName == ValueTaskTypeName)
        {
            return HandlerSignatureKind.VoidAsync;
        }

        if (returnType is INamedTypeSymbol namedType &&
            namedType.OriginalDefinition.ToDisplayString() == "System.Threading.Tasks.ValueTask<TResult>")
        {
            return HandlerSignatureKind.ResultAsync;
        }

        if (returnType.SpecialType != SpecialType.System_Void &&
            !returnTypeName.StartsWith("System.Threading.Tasks.Task", StringComparison.Ordinal) &&
            !returnTypeName.StartsWith("System.Threading.Tasks.ValueTask", StringComparison.Ordinal))
        {
            return HandlerSignatureKind.ResultSync;
        }

        return null;
    }

    private static (EquatableArray<string> YieldTypes, EquatableArray<string> SendTypes) GetAttributeTypeArrays(
        IMethodSymbol methodSymbol)
    {
        var yieldTypes = ImmutableArray<string>.Empty;
        var sendTypes = ImmutableArray<string>.Empty;

        foreach (var attr in methodSymbol.GetAttributes())
        {
            if (attr.AttributeClass?.ToDisplayString() != MessageHandlerAttributeName)
            {
                continue;
            }

            foreach (var namedArg in attr.NamedArguments)
            {
                if (namedArg.Key == "Yield" && !namedArg.Value.IsNull)
                {
                    yieldTypes = ExtractTypeArray(namedArg.Value);
                }
                else if (namedArg.Key == "Send" && !namedArg.Value.IsNull)
                {
                    sendTypes = ExtractTypeArray(namedArg.Value);
                }
            }
        }

        return (new EquatableArray<string>(yieldTypes), new EquatableArray<string>(sendTypes));
    }

    private static ImmutableArray<string> ExtractTypeArray(TypedConstant typedConstant)
    {
        if (typedConstant.Kind != TypedConstantKind.Array)
        {
            return ImmutableArray<string>.Empty;
        }

        var builder = ImmutableArray.CreateBuilder<string>();
        foreach (var value in typedConstant.Values)
        {
            if (value.Value is INamedTypeSymbol typeSymbol)
            {
                builder.Add(typeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat));
            }
        }

        return builder.ToImmutable();
    }

    private static EquatableArray<string> GetClassLevelTypes(INamedTypeSymbol classSymbol, string attributeName)
    {
        var builder = ImmutableArray.CreateBuilder<string>();

        foreach (var attr in classSymbol.GetAttributes())
        {
            if (attr.AttributeClass?.ToDisplayString() == attributeName &&
                attr.ConstructorArguments.Length > 0 &&
                attr.ConstructorArguments[0].Value is INamedTypeSymbol typeSymbol)
            {
                builder.Add(typeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat));
            }
        }

        return new EquatableArray<string>(builder.ToImmutable());
    }

    private static string GetContainingTypeChain(INamedTypeSymbol classSymbol)
    {
        var chain = new List<string>();
        var current = classSymbol.ContainingType;

        while (current != null)
        {
            chain.Insert(0, current.Name);
            current = current.ContainingType;
        }

        return string.Join(".", chain);
    }

    private static string? GetGenericParameters(INamedTypeSymbol classSymbol)
    {
        if (!classSymbol.IsGenericType)
        {
            return null;
        }

        var parameters = string.Join(", ", classSymbol.TypeParameters.Select(p => p.Name));
        return $"<{parameters}>";
    }
}

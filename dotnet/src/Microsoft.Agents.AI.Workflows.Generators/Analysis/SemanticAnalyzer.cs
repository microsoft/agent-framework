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
/// <remarks>
/// Analysis is split into two phases for efficiency with incremental generators:
/// <list type="number">
/// <item><see cref="AnalyzeMethod"/> - Called per method, extracts data and performs method-level validation only.</item>
/// <item><see cref="CombineMethodResults"/> - Groups methods by class and performs class-level validation once.</item>
/// </list>
/// This avoids redundant class validation when multiple handlers exist in the same class.
/// </remarks>
internal static class SemanticAnalyzer
{
    // Fully-qualified type names used for symbol comparison
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
    /// <remarks>
    /// This method only extracts raw data and performs method-level validation.
    /// Class-level validation is deferred to <see cref="CombineMethodResults"/> to avoid
    /// redundant validation when a class has multiple handler methods.
    /// </remarks>
    public static MethodAnalysisResult AnalyzeMethod(
        GeneratorAttributeSyntaxContext context,
        CancellationToken cancellationToken)
    {
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

        // Extract class-level info (raw facts, no validation here)
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

        // Get class location for class-level diagnostics
        var classLocation = GetClassLocation(classSymbol, cancellationToken);

        // Analyze the handler method (method-level validation only)
        // Skip method analysis if class doesn't derive from Executor (class-level diagnostic will be reported later)
        var methodDiagnostics = ImmutableArray.CreateBuilder<DiagnosticInfo>();
        HandlerInfo? handler = null;
        if (derivesFromExecutor)
        {
            handler = AnalyzeHandler(methodSymbol, methodSyntax, methodDiagnostics);
        }

        return new MethodAnalysisResult(
            classKey, @namespace, className, genericParameters, isNested, containingTypeChain,
            baseHasConfigureRoutes, classSendTypes, classYieldTypes,
            isPartialClass, derivesFromExecutor, hasManualConfigureRoutes,
            classLocation,
            handler,
            Diagnostics: new ImmutableEquatableArray<DiagnosticInfo>(methodDiagnostics.ToImmutable()));
    }

    /// <summary>
    /// Combines multiple MethodAnalysisResults for the same class into an AnalysisResult.
    /// Performs class-level validation once (instead of per-method) for efficiency.
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
        var classLocation = first.ClassLocation?.ToRoslynLocation() ?? Location.None;

        // Collect method-level diagnostics
        var allDiagnostics = ImmutableArray.CreateBuilder<Diagnostic>();
        foreach (var method in methods)
        {
            foreach (var diag in method.Diagnostics)
            {
                allDiagnostics.Add(diag.ToRoslynDiagnostic(null));
            }
        }

        // Class-level validation (done once, not per-method)
        if (!first.DerivesFromExecutor)
        {
            allDiagnostics.Add(Diagnostic.Create(
                DiagnosticDescriptors.NotAnExecutor,
                classLocation,
                first.ClassName,
                first.ClassName));
            return AnalysisResult.WithDiagnostics(allDiagnostics.ToImmutable());
        }

        if (!first.IsPartialClass)
        {
            allDiagnostics.Add(Diagnostic.Create(
                DiagnosticDescriptors.ClassMustBePartial,
                classLocation,
                first.ClassName));
            return AnalysisResult.WithDiagnostics(allDiagnostics.ToImmutable());
        }

        if (first.HasManualConfigureRoutes)
        {
            allDiagnostics.Add(Diagnostic.Create(
                DiagnosticDescriptors.ConfigureRoutesAlreadyDefined,
                classLocation,
                first.ClassName));
            return AnalysisResult.WithDiagnostics(allDiagnostics.ToImmutable());
        }

        // Collect valid handlers
        var handlers = methods
            .Where(m => m.Handler is not null)
            .Select(m => m.Handler!)
            .ToImmutableArray();

        if (handlers.Length == 0)
        {
            return AnalysisResult.WithDiagnostics(allDiagnostics.ToImmutable());
        }

        var executorInfo = new ExecutorInfo(
            first.Namespace,
            first.ClassName,
            first.GenericParameters,
            first.IsNested,
            first.ContainingTypeChain,
            first.BaseHasConfigureRoutes,
            new ImmutableEquatableArray<HandlerInfo>(handlers),
            first.ClassSendTypes,
            first.ClassYieldTypes);

        if (allDiagnostics.Count > 0)
        {
            return AnalysisResult.WithInfoAndDiagnostics(executorInfo, allDiagnostics.ToImmutable());
        }

        return AnalysisResult.Success(executorInfo);
    }

    /// <summary>
    /// Creates a placeholder result for invalid targets (e.g., attribute on non-method).
    /// </summary>
    private static MethodAnalysisResult CreateEmptyResult()
    {
        return new MethodAnalysisResult(
            string.Empty, null, string.Empty, null, false, string.Empty,
            false, ImmutableEquatableArray<string>.Empty, ImmutableEquatableArray<string>.Empty,
            false, false, false,
            null, null, ImmutableEquatableArray<DiagnosticInfo>.Empty);
    }

    /// <summary>
    /// Gets the source location of the class identifier for diagnostic reporting.
    /// </summary>
    private static DiagnosticLocationInfo? GetClassLocation(INamedTypeSymbol classSymbol, CancellationToken cancellationToken)
    {
        foreach (var syntaxRef in classSymbol.DeclaringSyntaxReferences)
        {
            var syntax = syntaxRef.GetSyntax(cancellationToken);
            if (syntax is ClassDeclarationSyntax classDecl)
            {
                return DiagnosticLocationInfo.FromLocation(classDecl.Identifier.GetLocation());
            }
        }

        return null;
    }

    /// <summary>
    /// Returns a unique identifier for the class used to group methods by their containing type.
    /// </summary>
    private static string GetClassKey(INamedTypeSymbol classSymbol)
    {
        return classSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);
    }

    /// <summary>
    /// Checks if any declaration of the class has the 'partial' modifier.
    /// </summary>
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

    /// <summary>
    /// Walks the inheritance chain to check if the class derives from Executor or Executor&lt;T&gt;.
    /// </summary>
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

    /// <summary>
    /// Checks if this class directly defines ConfigureRoutes (not inherited).
    /// If so, we skip generation to avoid conflicting with user's manual implementation.
    /// </summary>
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

    /// <summary>
    /// Checks if any base class (between this class and Executor) defines ConfigureRoutes.
    /// If so, generated code should call base.ConfigureRoutes() to preserve inherited handlers.
    /// </summary>
    private static bool BaseHasConfigureRoutes(INamedTypeSymbol classSymbol)
    {
        var baseType = classSymbol.BaseType;
        while (baseType != null)
        {
            var fullName = baseType.OriginalDefinition.ToDisplayString();
            // Stop at Executor - its ConfigureRoutes is abstract/empty
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

    /// <summary>
    /// Validates a handler method's signature and extracts metadata.
    /// </summary>
    /// <remarks>
    /// Valid signatures:
    /// <list type="bullet">
    /// <item><c>void Handle(TMessage, IWorkflowContext, [CancellationToken])</c></item>
    /// <item><c>ValueTask HandleAsync(TMessage, IWorkflowContext, [CancellationToken])</c></item>
    /// <item><c>ValueTask&lt;TResult&gt; HandleAsync(TMessage, IWorkflowContext, [CancellationToken])</c></item>
    /// <item><c>TResult Handle(TMessage, IWorkflowContext, [CancellationToken])</c> (sync with result)</item>
    /// </list>
    /// </remarks>
    private static HandlerInfo? AnalyzeHandler(
        IMethodSymbol methodSymbol,
        MethodDeclarationSyntax? methodSyntax,
        ImmutableArray<DiagnosticInfo>.Builder diagnostics)
    {
        var location = methodSyntax?.Identifier.GetLocation() ?? Location.None;

        // Check if static
        if (methodSymbol.IsStatic)
        {
            diagnostics.Add(DiagnosticInfo.Create("MAFGENWF007", location, methodSymbol.Name));
            return null;
        }

        // Check parameter count
        if (methodSymbol.Parameters.Length < 2)
        {
            diagnostics.Add(DiagnosticInfo.Create("MAFGENWF005", location, methodSymbol.Name));
            return null;
        }

        // Check second parameter is IWorkflowContext
        var secondParam = methodSymbol.Parameters[1];
        if (secondParam.Type.ToDisplayString() != WorkflowContextTypeName)
        {
            diagnostics.Add(DiagnosticInfo.Create("MAFGENWF001", location, methodSymbol.Name));
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
            diagnostics.Add(DiagnosticInfo.Create("MAFGENWF002", location, methodSymbol.Name));
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

    /// <summary>
    /// Determines the handler signature kind from the return type.
    /// </summary>
    /// <returns>The signature kind, or null if the return type is not supported (e.g., Task, Task&lt;T&gt;).</returns>
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

        // Any non-void, non-Task type is treated as a synchronous result
        if (returnType.SpecialType != SpecialType.System_Void &&
            !returnTypeName.StartsWith("System.Threading.Tasks.Task", StringComparison.Ordinal) &&
            !returnTypeName.StartsWith("System.Threading.Tasks.ValueTask", StringComparison.Ordinal))
        {
            return HandlerSignatureKind.ResultSync;
        }

        // Task/Task<T> not supported - must use ValueTask
        return null;
    }

    /// <summary>
    /// Extracts Yield and Send type arrays from the [MessageHandler] attribute's named arguments.
    /// </summary>
    /// <example>
    /// [MessageHandler(Yield = new[] { typeof(OutputA), typeof(OutputB) }, Send = new[] { typeof(Request) })]
    /// </example>
    private static (ImmutableEquatableArray<string> YieldTypes, ImmutableEquatableArray<string> SendTypes) GetAttributeTypeArrays(
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

        return (new ImmutableEquatableArray<string>(yieldTypes), new ImmutableEquatableArray<string>(sendTypes));
    }

    /// <summary>
    /// Converts a TypedConstant array (from attribute argument) to fully-qualified type name strings.
    /// </summary>
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

    /// <summary>
    /// Collects types from [SendsMessage] or [YieldsMessage] attributes applied to the class.
    /// </summary>
    /// <example>
    /// [SendsMessage(typeof(Request))]
    /// [YieldsMessage(typeof(Response))]
    /// public partial class MyExecutor : Executor { }
    /// </example>
    private static ImmutableEquatableArray<string> GetClassLevelTypes(INamedTypeSymbol classSymbol, string attributeName)
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

        return new ImmutableEquatableArray<string>(builder.ToImmutable());
    }

    /// <summary>
    /// Builds the chain of containing types for nested classes, outermost first.
    /// </summary>
    /// <example>
    /// For class Outer.Middle.Inner.MyExecutor, returns "Outer.Middle.Inner"
    /// </example>
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

    /// <summary>
    /// Returns the generic type parameter clause (e.g., "&lt;T, U&gt;") for generic classes, or null for non-generic.
    /// </summary>
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

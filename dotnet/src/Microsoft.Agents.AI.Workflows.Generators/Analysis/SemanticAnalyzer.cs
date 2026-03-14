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
/// <item><see cref="AnalyzeHandlerMethod"/> - Called per method, extracts data and performs method-level validation only.</item>
/// <item><see cref="CombineHandlerMethodResults"/> - Groups methods by class and performs class-level validation once.</item>
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
    private const string YieldsOutputAttributeName = "Microsoft.Agents.AI.Workflows.YieldsOutputAttribute";

    /// <summary>
    /// Analyzes a method with [MessageHandler] attribute found by ForAttributeWithMetadataName.
    /// Returns a MethodAnalysisResult containing both method info and class context.
    /// </summary>
    /// <remarks>
    /// This method only extracts raw data and performs method-level validation.
    /// Class-level validation is deferred to <see cref="CombineHandlerMethodResults"/> to avoid
    /// redundant validation when a class has multiple handler methods.
    /// </remarks>
    public static MethodAnalysisResult AnalyzeHandlerMethod(
        GeneratorAttributeSyntaxContext context,
        CancellationToken cancellationToken)
    {
        // The target should be a method
        if (context.TargetSymbol is not IMethodSymbol methodSymbol)
        {
            return MethodAnalysisResult.Empty;
        }

        // Get the containing class
        INamedTypeSymbol? classSymbol = methodSymbol.ContainingType;
        if (classSymbol is null)
        {
            return MethodAnalysisResult.Empty;
        }

        // Get the method syntax for location info
        MethodDeclarationSyntax? methodSyntax = context.TargetNode as MethodDeclarationSyntax;

        // Extract class-level info (raw facts, no validation here)
        string classKey = GetClassKey(classSymbol);
        bool isPartialClass = IsPartialClass(classSymbol, cancellationToken);
        bool derivesFromExecutor = DerivesFromExecutor(classSymbol);
        bool configureProtocol = HasConfigureProtocolDefined(classSymbol);

        // Extract class metadata
        string? @namespace = classSymbol.ContainingNamespace?.IsGlobalNamespace == true
            ? null
            : classSymbol.ContainingNamespace?.ToDisplayString();
        string className = classSymbol.Name;
        string? genericParameters = GetGenericParameters(classSymbol);
        bool isNested = classSymbol.ContainingType != null;
        string containingTypeChain = GetContainingTypeChain(classSymbol);
        bool baseHasConfigureProtocol = BaseHasConfigureProtocol(classSymbol);
        ImmutableEquatableArray<string> classSendTypes = GetClassLevelTypes(classSymbol, SendsMessageAttributeName);
        ImmutableEquatableArray<string> classYieldTypes = GetClassLevelTypes(classSymbol, YieldsOutputAttributeName);

        // Get class location for class-level diagnostics
        DiagnosticLocationInfo? classLocation = GetClassLocation(classSymbol, cancellationToken);

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
            baseHasConfigureProtocol, classSendTypes, classYieldTypes,
            isPartialClass, derivesFromExecutor, configureProtocol,
            classLocation,
            handler,
            Diagnostics: new ImmutableEquatableArray<DiagnosticInfo>(methodDiagnostics.ToImmutable()));
    }

    /// <summary>
    /// Combines multiple MethodAnalysisResults for the same class into an AnalysisResult.
    /// Performs class-level validation once (instead of per-method) for efficiency.
    /// </summary>
    public static AnalysisResult CombineHandlerMethodResults(IEnumerable<MethodAnalysisResult> methodResults)
    {
        List<MethodAnalysisResult> methods = methodResults.ToList();
        if (methods.Count == 0)
        {
            return AnalysisResult.Empty;
        }

        // All methods should have same class info - take from first
        MethodAnalysisResult first = methods[0];
        Location classLocation = first.ClassLocation?.ToRoslynLocation() ?? Location.None;

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
                DiagnosticDescriptors.ConfigureProtocolAlreadyDefined,
                classLocation,
                first.ClassName));
            return AnalysisResult.WithDiagnostics(allDiagnostics.ToImmutable());
        }

        // Collect valid handlers
        ImmutableArray<HandlerInfo> handlers = methods
            .Where(m => m.Handler is not null)
            .Select(m => m.Handler!)
            .ToImmutableArray();

        if (handlers.Length == 0)
        {
            return AnalysisResult.WithDiagnostics(allDiagnostics.ToImmutable());
        }

        ExecutorInfo executorInfo = new(
            first.Namespace,
            first.ClassName,
            first.GenericParameters,
            first.IsNested,
            first.ContainingTypeChain,
            first.BaseHasConfigureProtocol,
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
    /// Analyzes a class with [SendsMessage] or [YieldsOutput] attribute found by ForAttributeWithMetadataName.
    /// Returns ClassProtocolInfo entries for each attribute instance (handles multiple attributes of same type).
    /// </summary>
    /// <param name="context">The generator attribute syntax context.</param>
    /// <param name="attributeKind">Whether this is a Send or Yield attribute.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The analysis results for the class protocol attributes.</returns>
    public static ImmutableArray<ClassProtocolInfo> AnalyzeClassProtocolAttribute(
        GeneratorAttributeSyntaxContext context,
        ProtocolAttributeKind attributeKind,
        CancellationToken cancellationToken)
    {
        // The target should be a class
        if (context.TargetSymbol is not INamedTypeSymbol classSymbol)
        {
            return ImmutableArray<ClassProtocolInfo>.Empty;
        }

        // Extract class-level info (same for all attributes)
        string classKey = GetClassKey(classSymbol);
        bool isPartialClass = IsPartialClass(classSymbol, cancellationToken);
        bool derivesFromExecutor = DerivesFromExecutor(classSymbol);
        bool hasManualConfigureProtocol = HasConfigureProtocolDefined(classSymbol);

        string? @namespace = classSymbol.ContainingNamespace?.IsGlobalNamespace == true
            ? null
            : classSymbol.ContainingNamespace?.ToDisplayString();
        string className = classSymbol.Name;
        string? genericParameters = GetGenericParameters(classSymbol);
        bool isNested = classSymbol.ContainingType != null;
        string containingTypeChain = GetContainingTypeChain(classSymbol);
        DiagnosticLocationInfo? classLocation = GetClassLocation(classSymbol, cancellationToken);

        // Extract a ClassProtocolInfo for each attribute instance
        ImmutableArray<ClassProtocolInfo>.Builder results = ImmutableArray.CreateBuilder<ClassProtocolInfo>();

        foreach (AttributeData attr in context.Attributes)
        {
            if (attr.ConstructorArguments.Length > 0 &&
                attr.ConstructorArguments[0].Value is INamedTypeSymbol typeSymbol)
            {
                string typeName = typeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);
                results.Add(new ClassProtocolInfo(
                    classKey,
                    @namespace,
                    className,
                    genericParameters,
                    isNested,
                    containingTypeChain,
                    isPartialClass,
                    derivesFromExecutor,
                    hasManualConfigureProtocol,
                    classLocation,
                    typeName,
                    attributeKind));
            }
        }

        return results.ToImmutable();
    }

    /// <summary>
    /// Combines ClassProtocolInfo results into an AnalysisResult for classes that only have IO attributes
    /// (no [MessageHandler] methods). This generates only .SendsMessage/.YieldsMessage calls in the protocol
    /// configuration.
    /// </summary>
    /// <remarks>
    /// This is likely to be seen combined with the basic one-method <c>Executor%lt;TIn&gt;</c> or <c>Executor&lt;TIn, TOut&gt;</c>
    /// </remarks>
    /// <param name="protocolInfos">The protocol info entries for the class.</param>
    /// <returns>The combined analysis result.</returns>
    public static AnalysisResult CombineOutputOnlyResults(IEnumerable<ClassProtocolInfo> protocolInfos)
    {
        List<ClassProtocolInfo> protocols = protocolInfos.ToList();
        if (protocols.Count == 0)
        {
            return AnalysisResult.Empty;
        }

        // All entries should have same class info - take from first
        ClassProtocolInfo first = protocols[0];
        Location classLocation = first.ClassLocation?.ToRoslynLocation() ?? Location.None;

        ImmutableArray<Diagnostic>.Builder allDiagnostics = ImmutableArray.CreateBuilder<Diagnostic>();

        // Class-level validation
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

        // Collect send and yield types
        ImmutableArray<string>.Builder sendTypes = ImmutableArray.CreateBuilder<string>();
        ImmutableArray<string>.Builder yieldTypes = ImmutableArray.CreateBuilder<string>();

        foreach (ClassProtocolInfo protocol in protocols)
        {
            if (protocol.AttributeKind == ProtocolAttributeKind.Send)
            {
                sendTypes.Add(protocol.TypeName);
            }
            else
            {
                yieldTypes.Add(protocol.TypeName);
            }
        }

        // Sort to ensure consistent ordering for incremental generator caching
        sendTypes.Sort(StringComparer.Ordinal);
        yieldTypes.Sort(StringComparer.Ordinal);

        // Create ExecutorInfo with no handlers but with protocol types
        ExecutorInfo executorInfo = new(
            first.Namespace,
            first.ClassName,
            first.GenericParameters,
            first.IsNested,
            first.ContainingTypeChain,
            BaseHasConfigureProtocol: false, // Not relevant for protocol-only
            Handlers: ImmutableEquatableArray<HandlerInfo>.Empty,
            ClassSendTypes: new ImmutableEquatableArray<string>(sendTypes.ToImmutable()),
            ClassYieldTypes: new ImmutableEquatableArray<string>(yieldTypes.ToImmutable()));

        if (allDiagnostics.Count > 0)
        {
            return AnalysisResult.WithInfoAndDiagnostics(executorInfo, allDiagnostics.ToImmutable());
        }

        return AnalysisResult.Success(executorInfo);
    }

    /// <summary>
    /// Gets the source location of the class identifier for diagnostic reporting.
    /// </summary>
    private static DiagnosticLocationInfo? GetClassLocation(INamedTypeSymbol classSymbol, CancellationToken cancellationToken)
    {
        foreach (SyntaxReference syntaxRef in classSymbol.DeclaringSyntaxReferences)
        {
            SyntaxNode syntax = syntaxRef.GetSyntax(cancellationToken);
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
        foreach (SyntaxReference syntaxRef in classSymbol.DeclaringSyntaxReferences)
        {
            SyntaxNode syntax = syntaxRef.GetSyntax(cancellationToken);
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
        INamedTypeSymbol? current = classSymbol.BaseType;
        while (current != null)
        {
            string fullName = current.OriginalDefinition.ToDisplayString();
            if (fullName == ExecutorTypeName || fullName.StartsWith(ExecutorTypeName + "<", StringComparison.Ordinal))
            {
                return true;
            }

            current = current.BaseType;
        }

        return false;
    }

    /// <summary>
    /// Checks if this class directly defines ConfigureProtocol (not inherited).
    /// If so, we skip generation to avoid conflicting with user's manual implementation.
    /// </summary>
    private static bool HasConfigureProtocolDefined(INamedTypeSymbol classSymbol)
    {
        foreach (var member in classSymbol.GetMembers("ConfigureProtocol"))
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
    /// Checks if any base class (between this class and Executor) defines ConfigureProtocol.
    /// If so, generated code should call base.ConfigureProtocol() to preserve inherited handlers.
    /// </summary>
    private static bool BaseHasConfigureProtocol(INamedTypeSymbol classSymbol)
    {
        INamedTypeSymbol? baseType = classSymbol.BaseType;
        while (baseType != null)
        {
            string fullName = baseType.OriginalDefinition.ToDisplayString();
            // Stop at Executor - its ConfigureProtocol is abstract/empty
            if (fullName == ExecutorTypeName)
            {
                return false;
            }

            foreach (var member in baseType.GetMembers("ConfigureProtocol"))
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
        Location location = methodSyntax?.Identifier.GetLocation() ?? Location.None;

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
        IParameterSymbol secondParam = methodSymbol.Parameters[1];
        if (secondParam.Type.ToDisplayString() != WorkflowContextTypeName)
        {
            diagnostics.Add(DiagnosticInfo.Create("MAFGENWF001", location, methodSymbol.Name));
            return null;
        }

        // Check for optional CancellationToken as third parameter
        bool hasCancellationToken = methodSymbol.Parameters.Length >= 3 &&
            methodSymbol.Parameters[2].Type.ToDisplayString() == CancellationTokenTypeName;

        // Analyze return type
        ITypeSymbol returnType = methodSymbol.ReturnType;
        HandlerSignatureKind? signatureKind = GetSignatureKind(returnType);
        if (signatureKind == null)
        {
            diagnostics.Add(DiagnosticInfo.Create("MAFGENWF002", location, methodSymbol.Name));
            return null;
        }

        // Get input type
        ITypeSymbol inputType = methodSymbol.Parameters[0].Type;
        string inputTypeName = inputType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);

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
        (ImmutableEquatableArray<string> yieldTypes, ImmutableEquatableArray<string> sendTypes) = GetAttributeTypeArrays(methodSymbol);

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
        string returnTypeName = returnType.ToDisplayString();

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
                if (namedArg.Key.Equals("Yield", StringComparison.Ordinal) && !namedArg.Value.IsNull)
                {
                    yieldTypes = ExtractTypeArray(namedArg.Value);
                }
                else if (namedArg.Key.Equals("Send", StringComparison.Ordinal) && !namedArg.Value.IsNull)
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
    /// <remarks>
    /// Results are sorted to ensure consistent ordering for incremental generator caching.
    /// </remarks>
    private static ImmutableArray<string> ExtractTypeArray(TypedConstant typedConstant)
    {
        if (typedConstant.Kind != TypedConstantKind.Array)
        {
            return ImmutableArray<string>.Empty;
        }

        ImmutableArray<string>.Builder builder = ImmutableArray.CreateBuilder<string>();
        foreach (TypedConstant value in typedConstant.Values)
        {
            if (value.Value is INamedTypeSymbol typeSymbol)
            {
                builder.Add(typeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat));
            }
        }

        // Sort to ensure consistent ordering for incremental generator caching
        builder.Sort(StringComparer.Ordinal);

        return builder.ToImmutable();
    }

    /// <summary>
    /// Collects types from [SendsMessage] or [YieldsOutput] attributes applied to the class.
    /// </summary>
    /// <remarks>
    /// Results are sorted to ensure consistent ordering for incremental generator caching,
    /// since GetAttributes() order is not guaranteed across partial class declarations.
    /// </remarks>
    /// <example>
    /// [SendsMessage(typeof(Request))]
    /// [YieldsOutput(typeof(Response))]
    /// public partial class MyExecutor : Executor { }
    /// </example>
    private static ImmutableEquatableArray<string> GetClassLevelTypes(INamedTypeSymbol classSymbol, string attributeName)
    {
        ImmutableArray<string>.Builder builder = ImmutableArray.CreateBuilder<string>();

        foreach (AttributeData attr in classSymbol.GetAttributes())
        {
            if (attr.AttributeClass?.ToDisplayString() == attributeName &&
                attr.ConstructorArguments.Length > 0 &&
                attr.ConstructorArguments[0].Value is INamedTypeSymbol typeSymbol)
            {
                builder.Add(typeSymbol.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat));
            }
        }

        // Sort to ensure consistent ordering for incremental generator caching
        builder.Sort(StringComparer.Ordinal);

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
        List<string> chain = new();
        INamedTypeSymbol? current = classSymbol.ContainingType;

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

        string parameters = string.Join(", ", classSymbol.TypeParameters.Select(p => p.Name));
        return $"<{parameters}>";
    }
}

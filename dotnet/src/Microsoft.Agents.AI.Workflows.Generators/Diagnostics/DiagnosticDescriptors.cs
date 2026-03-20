// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows.Generators.Diagnostics;

/// <summary>
/// Diagnostic descriptors for the executor route source generator.
/// </summary>
internal static class DiagnosticDescriptors
{
    private const string Category = "Microsoft.Agents.AI.Workflows.Generators";

    private static readonly Dictionary<string, DiagnosticDescriptor> s_descriptorsById = new();

    /// <summary>
    /// Gets a diagnostic descriptor by its ID.
    /// </summary>
    public static DiagnosticDescriptor? GetById(string id)
    {
        return s_descriptorsById.TryGetValue(id, out var descriptor) ? descriptor : null;
    }

    private static DiagnosticDescriptor Register(DiagnosticDescriptor descriptor)
    {
        s_descriptorsById[descriptor.Id] = descriptor;
        return descriptor;
    }

    /// <summary>
    /// MAFGENWF001: Handler method must have IWorkflowContext parameter.
    /// </summary>
    public static readonly DiagnosticDescriptor MissingWorkflowContext = Register(new(
        id: "MAFGENWF001",
        title: "Handler missing IWorkflowContext parameter",
        messageFormat: "Method '{0}' marked with [MessageHandler] must have IWorkflowContext as the second parameter",
        category: Category,
        defaultSeverity: DiagnosticSeverity.Error,
        isEnabledByDefault: true));

    /// <summary>
    /// MAFGENWF002: Handler method has invalid return type.
    /// </summary>
    public static readonly DiagnosticDescriptor InvalidReturnType = Register(new(
        id: "MAFGENWF002",
        title: "Handler has invalid return type",
        messageFormat: "Method '{0}' marked with [MessageHandler] must return void, ValueTask, or ValueTask<T>",
        category: Category,
        defaultSeverity: DiagnosticSeverity.Error,
        isEnabledByDefault: true));

    /// <summary>
    /// MAFGENWF003: Executor with [MessageHandler] must be partial.
    /// </summary>
    public static readonly DiagnosticDescriptor ClassMustBePartial = Register(new(
        id: "MAFGENWF003",
        title: "Executor with [MessageHandler] must be partial",
        messageFormat: "Class '{0}' contains [MessageHandler] methods but is not declared as partial",
        category: Category,
        defaultSeverity: DiagnosticSeverity.Error,
        isEnabledByDefault: true));

    /// <summary>
    /// MAFGENWF004: [MessageHandler] on non-Executor class.
    /// </summary>
    public static readonly DiagnosticDescriptor NotAnExecutor = Register(new(
        id: "MAFGENWF004",
        title: "[MessageHandler] on non-Executor class",
        messageFormat: "Method '{0}' is marked with [MessageHandler] but class '{1}' does not derive from Executor",
        category: Category,
        defaultSeverity: DiagnosticSeverity.Warning,
        isEnabledByDefault: true));

    /// <summary>
    /// MAFGENWF005: Handler method has insufficient parameters.
    /// </summary>
    public static readonly DiagnosticDescriptor InsufficientParameters = Register(new(
        id: "MAFGENWF005",
        title: "Handler has insufficient parameters",
        messageFormat: "Method '{0}' marked with [MessageHandler] must have at least 2 parameters (message and IWorkflowContext)",
        category: Category,
        defaultSeverity: DiagnosticSeverity.Error,
        isEnabledByDefault: true));

    /// <summary>
    /// MAFGENWF006: ConfigureRoutes already defined.
    /// </summary>
    public static readonly DiagnosticDescriptor ConfigureProtocolAlreadyDefined = Register(new(
        id: "MAFGENWF006",
        title: "ConfigureProtocol already defined",
        messageFormat: "Class '{0}' already defines ConfigureProtocol; [MessageHandler] methods will be ignored",
        category: Category,
        defaultSeverity: DiagnosticSeverity.Info,
        isEnabledByDefault: true));

    /// <summary>
    /// MAFGENWF007: Handler method is static.
    /// </summary>
    public static readonly DiagnosticDescriptor HandlerCannotBeStatic = Register(new(
        id: "MAFGENWF007",
        title: "Handler cannot be static",
        messageFormat: "Method '{0}' marked with [MessageHandler] cannot be static",
        category: Category,
        defaultSeverity: DiagnosticSeverity.Error,
        isEnabledByDefault: true));
}

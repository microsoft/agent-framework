// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents the signature kind of a message handler method.
/// </summary>
internal enum HandlerSignatureKind
{
    /// <summary>Void synchronous: void Handler(T, IWorkflowContext) or void Handler(T, IWorkflowContext, CT)</summary>
    VoidSync,

    /// <summary>Void asynchronous: ValueTask Handler(T, IWorkflowContext[, CT])</summary>
    VoidAsync,

    /// <summary>Result synchronous: TResult Handler(T, IWorkflowContext[, CT])</summary>
    ResultSync,

    /// <summary>Result asynchronous: ValueTask&lt;TResult&gt; Handler(T, IWorkflowContext[, CT])</summary>
    ResultAsync
}

/// <summary>
/// Contains information about a single message handler method.
/// Uses record for automatic value equality, which is required for incremental generator caching.
/// </summary>
/// <param name="MethodName">The name of the handler method.</param>
/// <param name="InputTypeName">The fully-qualified type name of the input message type.</param>
/// <param name="OutputTypeName">The fully-qualified type name of the output type, or null if the handler is void.</param>
/// <param name="SignatureKind">The signature kind of the handler.</param>
/// <param name="HasCancellationToken">Whether the handler method has a CancellationToken parameter.</param>
/// <param name="YieldTypes">The types explicitly declared in the Yield property of [MessageHandler].</param>
/// <param name="SendTypes">The types explicitly declared in the Send property of [MessageHandler].</param>
internal sealed record HandlerInfo(
    string MethodName,
    string InputTypeName,
    string? OutputTypeName,
    HandlerSignatureKind SignatureKind,
    bool HasCancellationToken,
    ImmutableEquatableArray<string> YieldTypes,
    ImmutableEquatableArray<string> SendTypes)
{
    /// <summary>
    /// Gets whether this handler returns a value (either sync or async).
    /// </summary>
    public bool HasOutput => this.SignatureKind == HandlerSignatureKind.ResultSync || this.SignatureKind == HandlerSignatureKind.ResultAsync;
}

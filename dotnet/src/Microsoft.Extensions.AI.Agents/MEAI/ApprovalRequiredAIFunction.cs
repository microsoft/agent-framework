// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Marks an existing <see cref="AIFunction"/> with additional metadata to indicate that it requires approval.
/// </summary>
/// <param name="function">The <see cref="AIFunction"/> that requires approval.</param>
public sealed class ApprovalRequiredAIFunction(AIFunction function) : DelegatingAIFunction(function)
{
    /// <summary>
    /// An optional callback that can be used to determine if the function call requires approval, instead of the default behavior, which is to always require approval.
    /// </summary>
    public Func<AIFunctionApprovalContext, ValueTask<bool>> RequiresApprovalCallback { get; set; } = delegate { return new ValueTask<bool>(true); };
}

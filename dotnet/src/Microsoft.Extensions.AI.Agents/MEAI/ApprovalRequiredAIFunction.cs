// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

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
    public Func<ApprovalContext, ValueTask<bool>> RequiresApprovalCallback { get; set; } = _ => new(true);

    /// <summary>
    /// Context object that provides information about the function call that requires approval.
    /// </summary>
    public sealed class ApprovalContext
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="ApprovalContext"/> class.
        /// </summary>
        /// <param name="functionCall">The <see cref="FunctionCallContent"/> containing the details of the invocation.</param>
        /// <exception cref="ArgumentNullException"><paramref name="functionCall"/> is null.</exception>
        public ApprovalContext(FunctionCallContent functionCall)
        {
            this.FunctionCall = Throw.IfNull(functionCall);
        }

        /// <summary>
        /// Gets the <see cref="FunctionCallContent"/> containing the details of the invocation that will be made if approval is granted.
        /// </summary>
        public FunctionCallContent FunctionCall { get; }
    }
}

// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Context object that provides information about the function call that requires approval.
/// </summary>
public class AIFunctionApprovalContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AIFunctionApprovalContext"/> class.
    /// </summary>
    /// <param name="functionCall">The <see cref="FunctionCallContent"/> containing the details of the invocation.</param>
    /// <exception cref="ArgumentNullException"></exception>
    public AIFunctionApprovalContext(FunctionCallContent functionCall)
    {
        this.FunctionCall = functionCall ?? throw new ArgumentNullException(nameof(functionCall));
    }

    /// <summary>
    /// Gets the <see cref="FunctionCallContent"/> containing the details of the invocation that will be made if approval is granted.
    /// </summary>
    public FunctionCallContent FunctionCall { get; }
}

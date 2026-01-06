// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Configuration options hosting AI Agents as an Executor.
/// </summary>
public sealed class AIAgentHostOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether agent streaming update events should be emitted during execution.
    /// If <see langword="null"/>, the value will be taken from the <see cref="TurnToken"/>
    /// </summary>
    public bool? EmitAgentRunUpdateEvents { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether aggregated agent response events should be emitted during execution.
    /// </summary>
    public bool EmitAgentRunResponseEvents { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether <see cref="UserInputRequestContent"/> should be intercepted and sent
    /// as a message to the workflow for handling, instead of being raised as a request.
    /// </summary>
    public bool InterceptUserInputRequests { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether <see cref="FunctionCallContent"/> without a corresponding
    /// <see cref="FunctionResultContent"/> should be intercepted and sent as a message to the workflow for handling,
    /// instead of being raised as a request.
    /// </summary>
    public bool InterceptUnterminatedFunctionCalls { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether other messages from other agents should be assigned to the
    /// <see cref="ChatRole.User"/> role during execution.
    /// </summary>
    public bool ReassignOtherAgentsAsUsers { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether incoming messages are automatically forwarded before new messages generated
    /// by the agent during its turn.
    /// </summary>
    public bool ForwardIncomingMessages { get; set; } = true;
}

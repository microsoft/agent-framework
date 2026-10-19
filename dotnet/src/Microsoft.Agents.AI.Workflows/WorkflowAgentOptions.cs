// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Configuration options for hosting a <see cref="Workflow"/> as an <see cref="AIAgent"/>.
/// </summary>
public sealed class WorkflowAgentOptions
{
    /// <summary>
    /// Gets or sets a unique id for the hosting <see cref="AIAgent"/>.
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets a name for the hosting <see cref="AIAgent"/>.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets a description for the hosting <see cref="AIAgent"/>.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the execution environment to use when running the workflow. See
    /// <see cref="InProcessExecution.OffThread"/>, <see cref="InProcessExecution.Concurrent"/> and
    /// <see cref="InProcessExecution.Lockstep"/> for the in-process environments.
    /// </summary>
    public IWorkflowExecutionEnvironment? ExecutionEnvironment { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether <see cref="System.Exception.Message"/> should be included
    /// in the <see cref="ErrorContent"/> representing the workflow error.
    /// </summary>
    public bool IncludeExceptionDetails { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether outgoing workflow outputs should be transformed
    /// into content in <see cref="AgentResponseUpdate"/>s or the <see cref="AgentResponse"/> as appropriate.
    /// </summary>
    public bool IncludeWorkflowOutputsInResponse { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="ChatHistoryProvider"/> used to store the conversation history of the hosting <see cref="AIAgent"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When set, the provider is notified via <see cref="ChatHistoryProvider.InvokedAsync"/> at the end of each run
    /// with the request messages and the response messages, and it can be retrieved from the agent via
    /// <see cref="AIAgent.GetService(System.Type, object?)"/>.
    /// </para>
    /// <para>
    /// The workflow maintains its own conversation state, so only the new request messages are passed to the workflow on each run,
    /// and the provider is not asked to supply prior chat history via <see cref="ChatHistoryProvider.InvokingAsync"/>.
    /// </para>
    /// <para>
    /// When <see langword="null"/>, a default in-memory provider that stores the history in the session is used.
    /// </para>
    /// </remarks>
    public ChatHistoryProvider? ChatHistoryProvider { get; set; }

    internal WorkflowAgentOptions Clone() => (WorkflowAgentOptions)this.MemberwiseClone();
}

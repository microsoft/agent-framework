// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Options for running a durable agent.
/// </summary>
public sealed class DurableAgentRunOptions : AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableAgentRunOptions"/> class.
    /// </summary>
    public DurableAgentRunOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableAgentRunOptions"/> class by copying values from the specified options.
    /// </summary>
    /// <param name="options">The options instance from which to copy values.</param>
    private DurableAgentRunOptions(DurableAgentRunOptions options)
        : base(options)
    {
        this.EnableToolCalls = options.EnableToolCalls;
        this.EnableToolNames = options.EnableToolNames is not null ? new List<string>(options.EnableToolNames) : null;
        this.IsFireAndForget = options.IsFireAndForget;
    }

    /// <summary>
    /// Gets or sets whether to enable tool calls for this request.
    /// </summary>
    public bool EnableToolCalls { get; set; } = true;

    /// <summary>
    /// Gets or sets the collection of tool names to enable. If not specified, all tools are enabled.
    /// </summary>
    public IList<string>? EnableToolNames { get; set; }

    /// <summary>
    /// Gets or sets whether to fire and forget the agent run request.
    /// </summary>
    /// <remarks>
    /// If <see cref="IsFireAndForget"/> is <c>true</c>, the agent run request will be sent and the method will return immediately.
    /// The caller will not wait for the agent to complete the run and will not receive a response. This setting is useful for
    /// long-running tasks where the caller does not need to wait for the agent to complete the run.
    /// </remarks>
    public bool IsFireAndForget { get; set; }

    /// <inheritdoc/>
    public override AgentRunOptions Clone() => new DurableAgentRunOptions(this);
}

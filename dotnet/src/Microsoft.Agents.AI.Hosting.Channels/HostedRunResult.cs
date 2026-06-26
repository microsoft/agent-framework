// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Non-generic base for run results so channels and the host can pass them through capability
/// interfaces without committing to a result type. Inspect <see cref="ResultObject"/>
/// or cast to <see cref="HostedRunResult{TResult}"/> for typed access.
/// </summary>
public abstract class HostedRunResult
{
    /// <summary>Gets or sets the session attached to this result, when present.</summary>
    public ChannelSession? Session { get; set; }

    /// <summary>Gets the wrapped result as a boxed object.</summary>
    public abstract object? ResultObject { get; }
}

/// <summary>
/// Typed run result envelope. <typeparamref name="TResult"/> is <c>AgentRunResponse</c> for
/// agent targets and <c>WorkflowRunResponse</c> for workflow targets.
/// </summary>
public sealed class HostedRunResult<TResult> : HostedRunResult
{
    /// <summary>Gets the typed result.</summary>
    public TResult Result { get; }

    /// <inheritdoc />
    public override object? ResultObject => this.Result;

    /// <summary>Initializes a new instance of <see cref="HostedRunResult{TResult}"/>.</summary>
    /// <param name="result">The typed result.</param>
    public HostedRunResult(TResult result)
    {
        this.Result = result;
    }

    /// <summary>
    /// Shallow clone with a rewritten <see cref="Result"/>; used by per-destination
    /// <see cref="IChannelResponseHook"/> rebinds.
    /// </summary>
    public HostedRunResult<TNew> Replace<TNew>(TNew newResult) =>
        new(newResult) { Session = this.Session };
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides optional parameters and configuration settings for controlling agent run behavior.
/// </summary>
/// <remarks>
/// <para>
/// Implementations of <see cref="AIAgent"/> may provide subclasses of <see cref="AgentRunOptions"/> with additional options specific to that agent type.
/// </para>
/// </remarks>
public class AgentRunOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class.
    /// </summary>
    public AgentRunOptions()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunOptions"/> class by copying values from the specified options.
    /// </summary>
    /// <param name="options">The options instance from which to copy values.</param>
    /// <exception cref="ArgumentNullException"><paramref name="options"/> is <see langword="null"/>.</exception>
    public AgentRunOptions(AgentRunOptions options)
    {
        _ = Throw.IfNull(options);
        this.ContinuationToken = options.ContinuationToken;
        this.AllowBackgroundResponses = options.AllowBackgroundResponses;
        this.AdditionalProperties = options.AdditionalProperties?.Clone();
    }

    /// <summary>
    /// Gets or sets the continuation token for resuming and getting the result of the agent response identified by this token.
    /// </summary>
    /// <remarks>
    /// This property is used for background responses that can be activated via the <see cref="AllowBackgroundResponses"/>
    /// property if the <see cref="AIAgent"/> implementation supports them.
    /// Streamed background responses, such as those returned by default by <see cref="AIAgent.RunStreamingAsync(AgentThread?, AgentRunOptions?, System.Threading.CancellationToken)"/>
    /// can be resumed if interrupted. This means that a continuation token obtained from the <see cref="AgentRunResponseUpdate.ContinuationToken"/>
    /// of an update just before the interruption occurred can be passed to this property to resume the stream from the point of interruption.
    /// Non-streamed background responses, such as those returned by <see cref="AIAgent.RunAsync(AgentThread?, AgentRunOptions?, System.Threading.CancellationToken)"/>,
    /// can be polled for completion by obtaining the token from the <see cref="AgentRunResponse.ContinuationToken"/> property
    /// and passing it via this property on subsequent calls to <see cref="AIAgent.RunAsync(AgentThread?, AgentRunOptions?, System.Threading.CancellationToken)"/>.
    /// </remarks>
    public object? ContinuationToken { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the background responses are allowed.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Background responses allow running long-running operations or tasks asynchronously in the background that can be resumed by streaming APIs
    /// and polled for completion by non-streaming APIs.
    /// </para>
    /// <para>
    /// When this property is set to true, non-streaming APIs may start a background operation and return an initial
    /// response with a continuation token. Subsequent calls to the same API should be made in a polling manner with
    /// the continuation token to get the final result of the operation.
    /// </para>
    /// <para>
    /// When this property is set to true, streaming APIs may also start a background operation and begin streaming
    /// response updates until the operation is completed. If the streaming connection is interrupted, the
    /// continuation token obtained from the last update that has one should be supplied to a subsequent call to the same streaming API
    /// to resume the stream from the point of interruption and continue receiving updates until the operation is completed.
    /// </para>
    /// <para>
    /// This property only takes effect if the implementation it's used with supports background responses.
    /// If the implementation does not support background responses, this property will be ignored.
    /// </para>
    /// </remarks>
    public bool? AllowBackgroundResponses { get; set; }

    /// <summary>
    /// Gets or sets additional properties associated with these options.
    /// </summary>
    /// <value>
    /// An <see cref="AdditionalPropertiesDictionary"/> containing custom properties,
    /// or <see langword="null"/> if no additional properties are present.
    /// </value>
    /// <remarks>
    /// Additional properties provide a way to include custom metadata or provider-specific
    /// information that doesn't fit into the standard options schema. This is useful for
    /// preserving implementation-specific details or extending the options with custom data.
    /// </remarks>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

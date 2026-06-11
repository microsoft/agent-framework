// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
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
    protected AgentRunOptions(AgentRunOptions options)
    {
        _ = Throw.IfNull(options);
        this.ContinuationToken = options.ContinuationToken;
        this.AllowBackgroundResponses = options.AllowBackgroundResponses;
        this.AdditionalProperties = options.AdditionalProperties?.Clone();
        this.ResponseFormat = options.ResponseFormat;
    }

    /// <summary>
    /// Gets or sets the continuation token for resuming and getting the result of the agent response identified by this token.
    /// </summary>
    /// <remarks>
    /// This property is used for background responses that can be activated via the <see cref="AllowBackgroundResponses"/>
    /// property if the <see cref="AIAgent"/> implementation supports them.
    /// Streamed background responses, such as those returned by default by <see cref="AIAgent.RunStreamingAsync(AgentSession?, AgentRunOptions?, System.Threading.CancellationToken)"/>
    /// can be resumed if interrupted. This means that a continuation token obtained from the <see cref="AgentResponseUpdate.ContinuationToken"/>
    /// of an update just before the interruption occurred can be passed to this property to resume the stream from the point of interruption.
    /// Non-streamed background responses, such as those returned by <see cref="AIAgent.RunAsync(AgentSession?, AgentRunOptions?, System.Threading.CancellationToken)"/>,
    /// can be polled for completion by obtaining the token from the <see cref="AgentResponse.ContinuationToken"/> property
    /// and passing it via this property on subsequent calls to <see cref="AIAgent.RunAsync(AgentSession?, AgentRunOptions?, System.Threading.CancellationToken)"/>.
    /// </remarks>
    [Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
    public ResponseContinuationToken? ContinuationToken { get; set; }

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

    /// <summary>
    /// Gets or sets the response format.
    /// </summary>
    /// <remarks>
    /// If <see langword="null"/>, no response format is specified and the agent will use its default.
    /// This property can be set to <see cref="ChatResponseFormat.Text"/> to specify that the response should be unstructured text,
    /// to <see cref="ChatResponseFormat.Json"/> to specify that the response should be structured JSON data, or
    /// an instance of <see cref="ChatResponseFormatJson"/> constructed with a specific JSON schema to request that the
    /// response be structured JSON data according to that schema. It is up to the agent implementation if or how
    /// to honor the request. If the agent implementation doesn't recognize the specific kind of <see cref="ChatResponseFormat"/>,
    /// it can be ignored.
    /// </remarks>
    public ChatResponseFormat? ResponseFormat { get; set; }

    /// <summary>
    /// Produces a clone of the current <see cref="AgentRunOptions"/> instance.
    /// </summary>
    /// <returns>
    /// A clone of the current <see cref="AgentRunOptions"/> instance.
    /// </returns>
    /// <remarks>
    /// <para>
    /// The clone will have the same values for all properties as the original instance. Any collections, like <see cref="AdditionalProperties"/>,
    /// are shallow-cloned, meaning a new collection instance is created, but any references contained by the collections are shared with the original.
    /// </para>
    /// <para>
    /// Derived types should override <see cref="Clone"/> to return an instance of the derived type.
    /// </para>
    /// </remarks>
    public virtual AgentRunOptions Clone() => new(this);
}

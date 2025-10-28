// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a single streaming response chunk from an <see cref="AIAgent"/>.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="AgentRunResponseUpdate"/> is so named because it represents updates
/// that layer on each other to form a single agent response. Conceptually, this combines the roles of
/// <see cref="AgentRunResponse"/> and <see cref="ChatMessage"/> in streaming output.
/// </para>
/// <para>
/// To get the text result of this response chunk, use the <see cref="Text"/> property or simply call <see cref="ToString()"/> on the <see cref="AgentRunResponseUpdate"/>.
/// </para>
/// <para>
/// The relationship between <see cref="AgentRunResponse"/> and <see cref="AgentRunResponseUpdate"/> is
/// codified in the <see cref="AgentRunResponseExtensions.ToAgentRunResponseAsync"/> and
/// <see cref="AgentRunResponse.ToAgentRunResponseUpdates"/>, which enable bidirectional conversions
/// between the two. Note, however, that the provided conversions may be lossy, for example if multiple
/// updates all have different <see cref="RawRepresentation"/> objects whereas there's only one slot for
/// such an object available in <see cref="AgentRunResponse.RawRepresentation"/>.
/// </para>
/// </remarks>
[DebuggerDisplay("[{Role}] {ContentForDebuggerDisplay}{EllipsesForDebuggerDisplay,nq}")]
public class AgentRunResponseUpdate
{
    /// <summary>The response update content items.</summary>
    private IList<AIContent>? _contents;

    /// <summary>The name of the author of the update.</summary>
    private string? _authorName;

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponseUpdate"/> class.</summary>
    [JsonConstructor]
    public AgentRunResponseUpdate()
    {
    }

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponseUpdate"/> class.</summary>
    /// <param name="role">The role of the author of the update.</param>
    /// <param name="content">The text content of the update.</param>
    public AgentRunResponseUpdate(ChatRole? role, string? content)
        : this(role, content is null ? null : [new TextContent(content)])
    {
    }

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponseUpdate"/> class.</summary>
    /// <param name="role">The role of the author of the update.</param>
    /// <param name="contents">The contents of the update.</param>
    public AgentRunResponseUpdate(ChatRole? role, IList<AIContent>? contents)
    {
        this.Role = role;
        this._contents = contents;
    }

    /// <summary>Initializes a new instance of the <see cref="AgentRunResponseUpdate"/> class.</summary>
    /// <param name="chatResponseUpdate">The <see cref="ChatResponseUpdate"/> from which to seed this <see cref="AgentRunResponseUpdate"/>.</param>
    public AgentRunResponseUpdate(ChatResponseUpdate chatResponseUpdate)
    {
        _ = Throw.IfNull(chatResponseUpdate);

        this.AdditionalProperties = chatResponseUpdate.AdditionalProperties;
        this.AuthorName = chatResponseUpdate.AuthorName;
        this.Contents = chatResponseUpdate.Contents;
        this.CreatedAt = chatResponseUpdate.CreatedAt;
        this.MessageId = chatResponseUpdate.MessageId;
        this.RawRepresentation = chatResponseUpdate;
        this.ResponseId = chatResponseUpdate.ResponseId;
        this.Role = chatResponseUpdate.Role;
        this.ContinuationToken = chatResponseUpdate.ContinuationToken;
    }

    /// <summary>Gets or sets the name of the author of the response update.</summary>
    public string? AuthorName
    {
        get => this._authorName;
        set => this._authorName = string.IsNullOrWhiteSpace(value) ? null : value;
    }

    /// <summary>Gets or sets the role of the author of the response update.</summary>
    public ChatRole? Role { get; set; }

    /// <summary>Gets the text of this update.</summary>
    /// <remarks>
    /// This property concatenates the text of all <see cref="TextContent"/> objects in <see cref="Contents"/>.
    /// </remarks>
    [JsonIgnore]
    public string Text => this._contents is not null ? this._contents.ConcatText() : string.Empty;

    /// <summary>Gets the user input requests associated with the response.</summary>
    /// <remarks>
    /// This property concatenates all <see cref="UserInputRequestContent"/> instances in the response.
    /// </remarks>
    [JsonIgnore]
    public IEnumerable<UserInputRequestContent> UserInputRequests => this._contents?.OfType<UserInputRequestContent>() ?? [];

    /// <summary>Gets or sets the agent run response update content items.</summary>
    [AllowNull]
    public IList<AIContent> Contents
    {
        get => this._contents ??= [];
        set => this._contents = value;
    }

    /// <summary>Gets or sets the raw representation of the response update from an underlying implementation.</summary>
    /// <remarks>
    /// If a <see cref="AgentRunResponseUpdate"/> is created to represent some underlying object from another object
    /// model, this property can be used to store that original object. This can be useful for debugging or
    /// for enabling a consumer to access the underlying object model if needed.
    /// </remarks>
    [JsonIgnore]
    public object? RawRepresentation { get; set; }

    /// <summary>Gets or sets additional properties for the update.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }

    /// <summary>Gets or sets the ID of the agent that produced the response.</summary>
    public string? AgentId { get; set; }

    /// <summary>Gets or sets the ID of the response of which this update is a part.</summary>
    public string? ResponseId { get; set; }

    /// <summary>Gets or sets the ID of the message of which this update is a part.</summary>
    /// <remarks>
    /// A single streaming response may be composed of multiple messages, each of which may be represented
    /// by multiple updates. This property is used to group those updates together into messages.
    ///
    /// Some providers may consider streaming responses to be a single message, and in that case
    /// the value of this property may be the same as the response ID.
    ///
    /// This value is used when <see cref="AgentRunResponseExtensions.ToAgentRunResponseAsync(IAsyncEnumerable{AgentRunResponseUpdate}, System.Threading.CancellationToken)"/>
    /// groups <see cref="AgentRunResponseUpdate"/> instances into <see cref="AgentRunResponse"/> instances.
    /// The value must be unique to each call to the underlying provider, and must be shared by
    /// all updates that are part of the same logical message within a streaming response.
    /// </remarks>
    public string? MessageId { get; set; }

    /// <summary>Gets or sets a timestamp for the response update.</summary>
    public DateTimeOffset? CreatedAt { get; set; }

    /// <summary>
    /// Gets or sets the continuation token for resuming the streamed agent response of which this update is a part.
    /// </summary>
    /// <remarks>
    /// <see cref="AIAgent"/> implementations that support background responses will return
    /// a continuation token on each update if background responses are allowed in <see cref="AgentRunOptions.AllowBackgroundResponses"/>
    /// except for the last update, for which the token will be <see langword="null"/>.
    /// <para>
    /// This property should be used for stream resumption, where the continuation token of the latest received update should be
    /// passed to <see cref="AgentRunOptions.ContinuationToken"/> on subsequent calls to <see cref="AIAgent.RunStreamingAsync(AgentThread?, AgentRunOptions?, System.Threading.CancellationToken)"/>
    /// to resume streaming from the point of interruption.
    /// </para>
    /// </remarks>
    public object? ContinuationToken { get; set; }

    /// <inheritdoc/>
    public override string ToString() => this.Text;

    /// <summary>Gets a <see cref="AIContent"/> object to display in the debugger display.</summary>
    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    [ExcludeFromCodeCoverage]
    private AIContent? ContentForDebuggerDisplay => this._contents is { Count: > 0 } ? this._contents[0] : null;

    /// <summary>Gets an indication for the debugger display of whether there's more content.</summary>
    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    [ExcludeFromCodeCoverage]
    private string EllipsesForDebuggerDisplay => this._contents is { Count: > 1 } ? ", ..." : string.Empty;
}

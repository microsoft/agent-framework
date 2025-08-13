// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents metadata for the original message or update that initiated a user input request.
/// </summary>
public class UserInputOriginalMetadata
{
    /// <summary>Gets or sets the ID of the chat message or update.</summary>
    public string? MessageId { get; set; }

    /// <summary>Gets or sets the name of the author of the message or update.</summary>
    public string? AuthorName { get; set; }

    /// <summary>Gets or sets any additional properties associated with the message or update.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }

    /// <summary>Gets or sets a timestamp for the response update.</summary>
    public DateTimeOffset? CreatedAt { get; set; }

    /// <summary>Gets or sets the ID of the response of which the update is a part.</summary>
    public string? ResponseId { get; set; }

    /// <summary>Gets or sets the raw representation of the chat message or update from an underlying implementation.</summary>
    [JsonIgnore]
    public object? RawRepresentation { get; set; }
}

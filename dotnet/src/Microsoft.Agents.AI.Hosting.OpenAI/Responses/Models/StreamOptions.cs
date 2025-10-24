// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Options for streaming responses. Only set this when you set stream: true.
/// </summary>
internal sealed record StreamOptions
{
    /// <summary>
    /// If set, an additional chunk will be streamed before the data: [DONE] message.
    /// The usage field on this chunk shows the token usage statistics for the entire request,
    /// and the choices field will always be an empty array.
    /// </summary>
    [JsonPropertyName("include_usage")]
    public bool? IncludeUsage { get; init; }

    /// <summary>
    /// When true, stream obfuscation will be enabled. Stream obfuscation adds random characters
    /// to an obfuscation field on streaming delta events to normalize payload sizes as a mitigation
    /// to certain side-channel attacks. These obfuscation fields are included by default, but add
    /// a small amount of overhead to the data stream. You can set include_obfuscation to false to
    /// optimize for bandwidth if you trust the network links between your application and the OpenAI API.
    /// </summary>
    [JsonPropertyName("include_obfuscation")]
    public bool? IncludeObfuscation { get; init; }
}

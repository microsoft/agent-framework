// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Runtime.Serialization;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Purview.Models.Common;

namespace Microsoft.Agents.AI.Purview.Models.Responses;

/// <summary>
/// The response of a process content evaluation.
/// </summary>
internal sealed class ProcessContentResponse
{
    /// <summary>
    /// Gets or sets the evaluation id.
    /// </summary>
    [Key]
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets the status of protection scope changes.
    /// </summary>
    [DataMember]
    [JsonPropertyName("protectionScopeState")]
    public ProtectionScopeState? ProtectionScopeState { get; set; }

    /// <summary>
    /// Gets or sets the policy actions to take.
    /// </summary>
    [DataMember]
    [JsonPropertyName("policyActions")]
    public IReadOnlyList<DlpActionInfo>? PolicyActions { get; set; }

    /// <summary>
    /// Gets or sets error information about the evaluation.
    /// </summary>
    [DataMember]
    [JsonPropertyName("processingErrors")]
    public IReadOnlyList<ProcessingError>? ProcessingErrors { get; set; }
}

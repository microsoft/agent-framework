// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AgentOrchestration_Conditionals;

/// <summary>
/// Represents an email input for spam detection and response generation.
/// </summary>
public sealed class Email
{
    [JsonPropertyName("email_id")]
    public string EmailId { get; set; } = string.Empty;

    [JsonPropertyName("email_content")]
    public string EmailContent { get; set; } = string.Empty;
}

/// <summary>
/// Represents the result of spam detection analysis.
/// </summary>
public sealed class DetectionResult
{
    [JsonPropertyName("is_spam")]
    public bool IsSpam { get; set; }

    [JsonPropertyName("reason")]
    public string Reason { get; set; } = string.Empty;
}

/// <summary>
/// Represents a generated email response.
/// </summary>
public sealed class EmailResponse
{
    [JsonPropertyName("response")]
    public string Response { get; set; } = string.Empty;
}

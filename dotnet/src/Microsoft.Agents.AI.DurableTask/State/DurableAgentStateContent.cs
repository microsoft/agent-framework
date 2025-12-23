// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Base class for durable agent state content types.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "$type")]
[JsonDerivedType(typeof(DurableAgentStateDataContent), "data")]
[JsonDerivedType(typeof(DurableAgentStateErrorContent), "error")]
[JsonDerivedType(typeof(DurableAgentStateFunctionCallContent), "functionCall")]
[JsonDerivedType(typeof(DurableAgentStateFunctionResultContent), "functionResult")]
[JsonDerivedType(typeof(DurableAgentStateHostedFileContent), "hostedFile")]
[JsonDerivedType(typeof(DurableAgentStateHostedVectorStoreContent), "hostedVectorStore")]
[JsonDerivedType(typeof(DurableAgentStateTextContent), "text")]
[JsonDerivedType(typeof(DurableAgentStateTextReasoningContent), "reasoning")]
[JsonDerivedType(typeof(DurableAgentStateUriContent), "uri")]
[JsonDerivedType(typeof(DurableAgentStateUsageContent), "usage")]
[JsonDerivedType(typeof(DurableAgentStateUnknownContent), "unknown")]
internal abstract class DurableAgentStateContent
{
    /// <summary>
    /// Gets any additional data found during deserialization that does not map to known properties.
    /// </summary>
    [JsonExtensionData]
    public IDictionary<string, JsonElement>? ExtensionData { get; set; }

    /// <summary>
    /// Converts this durable agent state content to an <see cref="AIContent"/>.
    /// </summary>
    /// <returns>A converted <see cref="AIContent"/> instance.</returns>
    public abstract AIContent ToAIContent();

    /// <summary>
    /// Creates a <see cref="DurableAgentStateContent"/> from an <see cref="AIContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="AIContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateContent"/> representing the original <see cref="AIContent"/>.</returns>
    public static DurableAgentStateContent FromAIContent(AIContent content)
    {
        return content switch
        {
            DataContent dataContent => DurableAgentStateDataContent.FromDataContent(dataContent),
            ErrorContent errorContent => DurableAgentStateErrorContent.FromErrorContent(errorContent),
            FunctionCallContent functionCallContent => DurableAgentStateFunctionCallContent.FromFunctionCallContent(functionCallContent),
            FunctionResultContent functionResultContent => DurableAgentStateFunctionResultContent.FromFunctionResultContent(functionResultContent),
            HostedFileContent hostedFileContent => DurableAgentStateHostedFileContent.FromHostedFileContent(hostedFileContent),
            HostedVectorStoreContent hostedVectorStoreContent => DurableAgentStateHostedVectorStoreContent.FromHostedVectorStoreContent(hostedVectorStoreContent),
            TextContent textContent => DurableAgentStateTextContent.FromTextContent(textContent),
            TextReasoningContent textReasoningContent => DurableAgentStateTextReasoningContent.FromTextReasoningContent(textReasoningContent),
            UriContent uriContent => DurableAgentStateUriContent.FromUriContent(uriContent),
            UsageContent usageContent => DurableAgentStateUsageContent.FromUsageContent(usageContent),
            _ => DurableAgentStateUnknownContent.FromUnknownContent(content)
        };
    }
}

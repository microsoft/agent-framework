// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// Shared constants for the Purview service.
/// </summary>
internal static class Constants
{
    /// <summary>
    /// The odata type property name used in requests and responses.
    /// </summary>
    public const string ODataTypePropertyName = "@odata.type";

    /// <summary>
    /// The OData Graph namespace used for odata types.
    /// </summary>
    public const string ODataGraphNamespace = "microsoft.graph";

    /// <summary>
    /// The name of the property that contains the conversation id.
    /// </summary>
    public const string ConversationId = "conversationId";

    /// <summary>
    /// The name of the property that contains the user id.
    /// </summary>
    public const string UserId = "userId";
}

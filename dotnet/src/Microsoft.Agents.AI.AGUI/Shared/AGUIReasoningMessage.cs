// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIReasoningMessage : AGUIMessage
{
    public AGUIReasoningMessage()
    {
        this.Role = AGUIRoles.Reasoning;
    }

    [JsonPropertyName("encryptedValue")]
    public string? EncryptedValue { get; set; }
}

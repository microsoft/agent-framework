// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUITextInputContent : AGUIInputContent
{
    public AGUITextInputContent()
    {
        this.Type = "text";
    }

    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;
}

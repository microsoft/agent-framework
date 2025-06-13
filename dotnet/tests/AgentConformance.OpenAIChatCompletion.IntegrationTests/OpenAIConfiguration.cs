// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace AgentConformance.OpenAIChatCompletion.IntegrationTests;

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.

[SuppressMessage("Performance", "CA1812:Internal class that is apparently never instantiated",
    Justification = "Configuration classes are instantiated through IConfiguration.")]
internal sealed class OpenAIConfiguration
{
    public string? ServiceId { get; set; }

    public string ChatModelId { get; set; }

    public string ApiKey { get; set; }
}

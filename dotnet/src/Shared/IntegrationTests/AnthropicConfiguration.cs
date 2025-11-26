// Copyright (c) Microsoft. All rights reserved.

namespace Shared.IntegrationTests;

#pragma warning disable CS8618 // Non-nullable field must contain a non-null value when exiting constructor. Consider adding the 'required' modifier or declaring as nullable.
#pragma warning disable CA1812 // Internal class that is apparently never instantiated.

internal sealed class AnthropicConfiguration
{
    public string? ServiceId { get; set; }

    public string ChatModelId { get; set; }

    public string ChatReasoningModelId { get; set; }

    public string ApiKey { get; set; }
}

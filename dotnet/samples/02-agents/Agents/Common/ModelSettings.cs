// Copyright (c) Microsoft. All rights reserved.

namespace Common;

public sealed class ModelSettings
{
    public const string SectionName = "Llm";

    public string Provider { get; set; } = "Bailian";
    public string ApiKey { get; set; } = "";
    public string Model { get; set; } = "qwen-plus";
    public string? Endpoint { get; set; }
}

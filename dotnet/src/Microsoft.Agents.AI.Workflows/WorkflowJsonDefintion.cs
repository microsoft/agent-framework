// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows;

[JsonSourceGenerationOptions(UseStringEnumConverter = true)]
[JsonSerializable(typeof(WorkflowJsonDefinitionData))]
internal partial class WorkflowJsonDefinitionJsonContext : JsonSerializerContext
{
}

internal class WorkflowJsonDefinitionData
{
    public string StartExecutorId { get; set; } = string.Empty;
    public IEnumerable<Edge> Edges { get; set; } = [];
    public IEnumerable<RequestPort> Ports { get; set; } = [];
    public IEnumerable<string> OutputExecutors { get; set; } = [];
}

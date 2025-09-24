// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// The thread implementation used by <see cref="OrchestratingAgent"/>.
/// </summary>
internal sealed class OrchestratingAgentThread : InMemoryAgentThread
{
    internal OrchestratingAgentThread() { }

    internal OrchestratingAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
        : base(serializedThreadState, jsonSerializerOptions) { }
}

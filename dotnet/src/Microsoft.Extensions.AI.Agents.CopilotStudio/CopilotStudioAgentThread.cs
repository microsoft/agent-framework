// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.CopilotStudio;

/// <summary>
/// A thread used with the Copilot Studio agent.
/// </summary>
public sealed class CopilotStudioAgentThread : AgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CopilotStudioAgentThread"/> class.
    /// </summary>
    internal CopilotStudioAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="CopilotStudioAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    internal CopilotStudioAgentThread(JsonElement serializedThreadState)
    {
        var state = JsonSerializer.Deserialize(
            serializedThreadState,
            CopilotStudioAgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        if (state?.ConversationId is string conversationId)
        {
            this.ConversationId = conversationId;
        }
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public override async Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        var state = new ThreadState
        {
            ConversationId = this.ConversationId
        };

        return JsonSerializer.SerializeToElement(state, CopilotStudioAgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState)));
    }

    /// <summary>
    /// Gets the A2A context id that is being used to communicate with the A2A service.
    /// </summary>
    public string? ConversationId { get; internal set; }

    internal sealed class ThreadState
    {
        [JsonPropertyName("conversationId")]
        public string? ConversationId { get; set; }
    }
}

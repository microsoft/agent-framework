// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// Extension methods for converting CreateResponse to input messages.
/// </summary>
internal static class RequestConverterExtensions
{
    /// <summary>
    /// Extracts input messages from the CreateResponse.
    /// </summary>
    /// <param name="createResponse">The CreateResponse to extract messages from.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use for deserialization (optional).</param>
    /// <returns>A collection of ChatMessage objects.</returns>
    public static IReadOnlyCollection<ChatMessage> GetInputMessages(this CreateResponse createResponse, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var inputMessages = createResponse.Input.GetInputMessages();
        return inputMessages.Select(m => m.ToChatMessage()).ToList();
    }
}

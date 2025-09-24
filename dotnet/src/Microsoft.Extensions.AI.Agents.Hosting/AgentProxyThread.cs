// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.Hosting;

/// <summary>
/// Represents an agent thread for a <see cref="AgentProxy"/>.
/// </summary>
internal sealed partial class AgentProxyThread : ServiceIdAgentThread
{
#if NET7_0_OR_GREATER
    [System.Diagnostics.CodeAnalysis.StringSyntax("Regex")]
#endif
    private const string ThreadValidationRegex = "^[a-zA-Z0-9_.\\-~]+$";

#if NET7_0_OR_GREATER
    /// <summary>
    /// Regular expression pattern for valid thread IDs.
    /// Thread IDs must be alphanumeric and can contain hyphens, underscores, dots, and tildes (RFC 3986 unreserved characters).
    /// </summary>
    [GeneratedRegex(ThreadValidationRegex, RegexOptions.Compiled)]
    private static partial Regex ValidIdPattern();
#else
    /// <summary>
    /// Regular expression pattern for valid thread IDs.
    /// Thread IDs must be alphanumeric and can contain hyphens, underscores, dots, and tildes (RFC 3986 unreserved characters).
    /// </summary>
    private static readonly Regex s_validIdPattern = new(ThreadValidationRegex, RegexOptions.Compiled);

    /// <summary>
    /// Regular expression pattern for valid thread IDs.
    /// Thread IDs must be alphanumeric and can contain hyphens, underscores, dots, and tildes (RFC 3986 unreserved characters).
    /// </summary>
    private static Regex ValidIdPattern() => s_validIdPattern;
#endif

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentProxyThread"/> class with the specified identifier.
    /// </summary>
    /// <param name="id">The unique identifier for the agent proxy thread.</param>
    internal AgentProxyThread(string id)
    {
        Throw.IfNullOrEmpty(id);
        ValidateId(id);
        this.ConversationId = id;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentProxyThread"/> class with the specified identifier.
    /// </summary>
    internal AgentProxyThread() : this(CreateId())
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentProxyThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    internal AgentProxyThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
        : base(serializedThreadState, jsonSerializerOptions)
    {
    }

    /// <summary>
    /// Gets the ID that the conversation state is stored under for the agent.
    /// </summary>
    public string? ConversationId
    {
        get => this.ServiceThreadId;
        private set => this.ServiceThreadId = value;
    }

    internal static string CreateId() => Guid.NewGuid().ToString("N");

    /// <summary>
    /// Validates that the provided ID matches the required pattern for thread IDs.
    /// </summary>
    /// <param name="id">The ID to validate.</param>
    /// <exception cref="ArgumentException">Thrown when the ID is not valid.</exception>
    private static void ValidateId(string id)
    {
        if (!ValidIdPattern().IsMatch(id))
        {
            throw new ArgumentException($"Thread ID '{id}' is not valid. Thread IDs must contain only alphanumeric characters, hyphens, underscores, dots, and tildes.", nameof(id));
        }
    }
}

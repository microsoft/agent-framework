// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIAgent"/> that invokes a remote agent hosted with the Invocations protocol
/// by sending plain-text HTTP POST requests to the <c>/invocations</c> endpoint.
/// </summary>
public sealed class InvocationsAIAgent : AIAgent
{
    private readonly HttpClient _httpClient;
    private readonly Uri _invocationsUri;

    /// <summary>
    /// Initializes a new instance of the <see cref="InvocationsAIAgent"/> class.
    /// </summary>
    /// <param name="agentEndpoint">
    /// The base URI of the hosted agent (e.g., <c>http://localhost:8089</c>).
    /// The <c>/invocations</c> path is appended automatically.
    /// </param>
    /// <param name="httpClient">Optional <see cref="HttpClient"/> to use. If <see langword="null"/>, a new instance is created.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional description for the agent.</param>
    public InvocationsAIAgent(
        Uri agentEndpoint,
        HttpClient? httpClient = null,
        string? name = null,
        string? description = null)
    {
        ArgumentNullException.ThrowIfNull(agentEndpoint);

        this._httpClient = httpClient ?? new HttpClient();

        // Ensure the base URI ends with a slash so that combining works correctly.
        var baseUri = agentEndpoint.AbsoluteUri.EndsWith('/')
            ? agentEndpoint
            : new Uri(agentEndpoint.AbsoluteUri + "/");
        this._invocationsUri = new Uri(baseUri, "invocations");

        this.Name = name ?? "invocations-agent";
        this.Description = description ?? "An agent that calls a remote Invocations protocol endpoint.";
    }

    /// <inheritdoc/>
    public override string? Name { get; }

    /// <inheritdoc/>
    public override string? Description { get; }

    /// <inheritdoc/>
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var inputText = GetLastUserText(messages);
        var responseText = await this.SendInvocationAsync(inputText, cancellationToken).ConfigureAwait(false);
        return new AgentResponse(new ChatMessage(ChatRole.Assistant, responseText));
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // The Invocations protocol returns a complete response (no SSE streaming),
        // so we yield a single update with the full text.
        var inputText = GetLastUserText(messages);
        var responseText = await this.SendInvocationAsync(inputText, cancellationToken).ConfigureAwait(false);

        yield return new AgentResponseUpdate
        {
            Role = ChatRole.Assistant,
            Contents = [new TextContent(responseText)],
        };
    }

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new InvocationsAgentSession());

    /// <inheritdoc/>
    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
        AgentSession session,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(JsonSerializer.SerializeToElement(new { }, jsonSerializerOptions));

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        CancellationToken cancellationToken = default)
        => new(new InvocationsAgentSession());

    private async Task<string> SendInvocationAsync(string input, CancellationToken cancellationToken)
    {
        using var content = new StringContent(input, System.Text.Encoding.UTF8, "text/plain");
        using var response = await this._httpClient.PostAsync(this._invocationsUri, content, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
    }

    private static string GetLastUserText(IEnumerable<ChatMessage> messages)
    {
        string? lastUserText = null;
        foreach (var message in messages)
        {
            if (message.Role == ChatRole.User)
            {
                lastUserText = message.Text;
            }
        }

        return lastUserText ?? string.Empty;
    }

    /// <summary>
    /// Minimal session for the invocations agent. No state is persisted.
    /// </summary>
    private sealed class InvocationsAgentSession : AgentSession;
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.A2A;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace A2A;

/// <summary>
/// Provides extension methods for <see cref="AgentCard"/> to simplify the creation of A2A agents.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between A2A SDK client <see cref="AgentCard"/> and <see cref="AIAgent"/>.
/// <para>
/// The addresses listed in the card decide where requests are sent, including any credentials attached to the
/// supplied <see cref="HttpClient"/>. By default only absolute <c>https</c> addresses are used; other addresses are
/// ignored, and an <see cref="InvalidOperationException"/> is thrown when none remain. Use
/// <see cref="A2AAgentOptions.AllowAgentCardHostsInsecureHttp"/> to accept <c>http</c> addresses and
/// <see cref="A2AAgentOptions.AgentCardAllowedHosts"/> to restrict the hosts a card may point to. Setting
/// <see cref="A2AAgentOptions.AgentCardAllowedHosts"/> is recommended whenever the card may come from an untrusted source.
/// </para>
/// <para>
/// To select gRPC, also reference the SDK's <c>A2A.Grpc</c> package,
/// call <c>A2A.Grpc.A2AGrpcClientRegistration.Register()</c> once during application startup,
/// and include <see cref="ProtocolBindingNames.Grpc"/> in <see cref="A2AClientOptions.PreferredBindings"/>.
/// gRPC is not registered automatically and is not included in the default bindings.
/// </para>
/// <para>
/// The caller is responsible for disposing any disposable client created by these methods after the agent is no longer
/// in use. Retrieve it through <see cref="AIAgent.GetService"/> with <see cref="IA2AClient"/> as the service type
/// and dispose it as an <see cref="IDisposable"/>.
/// </para>
/// </remarks>
public static class AgentCardExtensions
{
    /// <summary>
    /// Retrieves an instance of <see cref="A2AAgent"/> for an existing A2A agent.
    /// </summary>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// <para>
    /// This overload accepts any host listed in the card. If the card may come from an untrusted source, use the
    /// overload that takes <see cref="A2AAgentOptions"/> and set <see cref="A2AAgentOptions.AgentCardAllowedHosts"/>.
    /// </para>
    /// </remarks>
    /// <param name="card">The <see cref="AgentCard" /> to use for the agent creation.</param>
    /// <param name="httpClient">The <see cref="HttpClient"/> to use for HTTP requests.</param>
    /// <param name="options">
    /// Optional <see cref="A2AClientOptions"/> controlling protocol binding preference.
    /// When not provided, defaults to preferring HTTP+JSON first, with JSON-RPC as fallback.
    /// </param>
    /// <param name="loggerFactory">The logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="A2AAgent"/> instance backed by the A2A agent.</returns>
    public static A2AAgent AsAIAgent(this AgentCard card, HttpClient? httpClient = null, A2AClientOptions? options = null, ILoggerFactory? loggerFactory = null)
        => card.AsAIAgent(new A2AAgentOptions(), httpClient, options, loggerFactory);

    /// <summary>
    /// Retrieves an instance of <see cref="A2AAgent"/> for an existing A2A agent.
    /// </summary>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism. When <paramref name="agentOptions"/> is provided, any non-null values override
    /// the corresponding values from the <see cref="AgentCard"/>.
    /// </remarks>
    /// <param name="card">The <see cref="AgentCard" /> to use for the agent creation.</param>
    /// <param name="agentOptions">
    /// Configuration options that control the agent's identity and which card addresses may be used. When provided,
    /// non-null values override the corresponding values from the agent card. If the card may come from an untrusted
    /// source, setting <see cref="A2AAgentOptions.AgentCardAllowedHosts"/> is recommended.
    /// </param>
    /// <param name="httpClient">The <see cref="HttpClient"/> to use for HTTP requests.</param>
    /// <param name="clientOptions">
    /// Optional <see cref="A2AClientOptions"/> controlling protocol binding preference.
    /// When not provided, defaults to preferring HTTP+JSON first, with JSON-RPC as fallback.
    /// </param>
    /// <param name="loggerFactory">The logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="A2AAgent"/> instance backed by the A2A agent.</returns>
    public static A2AAgent AsAIAgent(this AgentCard card, A2AAgentOptions agentOptions, HttpClient? httpClient = null, A2AClientOptions? clientOptions = null, ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(card);
        _ = Throw.IfNull(agentOptions);

        var a2aClient = A2AClientFactory.Create(WithAllowedInterfacesOnly(card, agentOptions), httpClient, clientOptions);

        var mergedOptions = agentOptions.Clone();
        mergedOptions.Name ??= card.Name;
        mergedOptions.Description ??= card.Description;

        return a2aClient.AsAIAgent(mergedOptions, loggerFactory);
    }

    /// <summary>
    /// Returns a card that lists only the interfaces whose address passes the checks configured in
    /// <paramref name="agentOptions"/>. The supplied card is never modified.
    /// </summary>
    private static AgentCard WithAllowedInterfacesOnly(AgentCard card, A2AAgentOptions agentOptions)
    {
        // An unset list allows any host; an empty list allows none. Bad entries throw here.
        AllowedHttpHosts? allowedHosts = agentOptions.AgentCardAllowedHosts is { } hosts
            ? new AllowedHttpHosts(hosts, allowAnyPortWhenUnspecified: true)
            : null;

        // A card without interfaces is left for the client factory to reject.
        if (card.SupportedInterfaces is not { Count: > 0 } interfaces)
        {
            return card;
        }

        List<AgentInterface> allowed = [];
        foreach (var agentInterface in interfaces)
        {
            if (IsAllowedAddress(agentInterface?.Url, agentOptions, allowedHosts))
            {
                allowed.Add(agentInterface!);
            }
        }

        if (allowed.Count == interfaces.Count)
        {
            return card;
        }

        if (allowed.Count == 0)
        {
            throw new InvalidOperationException(
                "None of the addresses listed in the agent card are allowed. Addresses must be absolute and use https. " +
                $"Use {nameof(A2AAgentOptions)}.{nameof(A2AAgentOptions.AllowAgentCardHostsInsecureHttp)} to accept http addresses, " +
                $"and check {nameof(A2AAgentOptions)}.{nameof(A2AAgentOptions.AgentCardAllowedHosts)} if it is set.");
        }

        return new AgentCard
        {
            Name = card.Name,
            Description = card.Description,
            Version = card.Version,
            DocumentationUrl = card.DocumentationUrl,
            IconUrl = card.IconUrl,
            SupportedInterfaces = allowed,
            Capabilities = card.Capabilities,
            Provider = card.Provider,
            Skills = card.Skills,
            DefaultInputModes = card.DefaultInputModes,
            DefaultOutputModes = card.DefaultOutputModes,
            SecuritySchemes = card.SecuritySchemes,
            SecurityRequirements = card.SecurityRequirements,
            Signatures = card.Signatures,
        };
    }

    private static bool IsAllowedAddress(string? address, A2AAgentOptions agentOptions, AllowedHttpHosts? allowedHosts)
    {
        if (!Uri.TryCreate(address, UriKind.Absolute, out var uri))
        {
            return false;
        }

        bool schemeAllowed =
            string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) ||
            (agentOptions.AllowAgentCardHostsInsecureHttp && string.Equals(uri.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase));

        if (!schemeAllowed)
        {
            return false;
        }

        return allowedHosts?.Contains(uri) ?? true;
    }
}

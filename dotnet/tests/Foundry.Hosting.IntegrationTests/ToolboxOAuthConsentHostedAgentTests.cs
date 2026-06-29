// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// End-to-end test for the per-user OAuth toolbox consent flow. The hosted container pre-registers a
/// Foundry toolbox whose tool source needs per-user OAuth consent; invoking the agent must surface an
/// <c>oauth_consent_request</c> (carrying a consent link) to the consumer instead of silently running
/// without the tool, and the container must stay routable (no 424) despite the consent-gated toolbox.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class ToolboxOAuthConsentHostedAgentTests(ToolboxOAuthConsentHostedAgentFixture fixture)
    : IClassFixture<ToolboxOAuthConsentHostedAgentFixture>
{
    private readonly ToolboxOAuthConsentHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build, a consent-gated toolbox in the IT project, and end to end smoke (step 5).")]
    public async Task ToolRequiringConsent_SurfacesOAuthConsentRequestToConsumerAsync()
    {
        // Arrange: the agent is backed by a pre-registered toolbox whose tool source requires
        // per-user OAuth consent (the fixture provisioned it, the container stayed routable).
        var agent = this._fixture.Agent;

        // Act: ask for something that needs the OAuth-protected tool. The toolbox proxy returns
        // CONSENT_REQUIRED for the (unconsented) caller, which the hosted agent surfaces as an
        // oauth_consent_request output item and marks the response incomplete.
        var response = await agent.RunAsync(
            "Use the OAuth-protected tool to act on my behalf. List my pull requests.");

        // Assert: the consumer captured an oauth_consent_request carrying a usable https consent link.
        // The high-level client exposes the (non-OpenAI) consent item as an AIContent whose
        // RawRepresentation serializes to the oauth_consent_request wire shape, mirroring how the
        // Hosted-Toolbox-AuthPaths REPL client detects it.
        var consentLink = response.Messages
            .SelectMany(m => m.Contents)
            .Select(c => TryGetConsentLink(c.RawRepresentation))
            .FirstOrDefault(link => link is not null);

        Assert.False(string.IsNullOrWhiteSpace(consentLink),
            "Expected the response to surface an oauth_consent_request with a consent link.");
        Assert.StartsWith("https://", consentLink, StringComparison.OrdinalIgnoreCase);
    }

    private static string? TryGetConsentLink(object? raw)
    {
        if (raw is null)
        {
            return null;
        }

        try
        {
            BinaryData json = ModelReaderWriter.Write(raw, new ModelReaderWriterOptions("J"));
            using JsonDocument doc = JsonDocument.Parse(json);
            JsonElement root = doc.RootElement;
            if (root.ValueKind == JsonValueKind.Object
                && root.TryGetProperty("type", out JsonElement typeProp)
                && typeProp.GetString() == "oauth_consent_request"
                && root.TryGetProperty("consent_link", out JsonElement linkProp)
                && linkProp.GetString() is string link
                && !string.IsNullOrWhiteSpace(link))
            {
                return link;
            }
        }
        catch (Exception ex) when (ex is JsonException or InvalidOperationException or NotSupportedException or FormatException)
        {
            // Not a persistable model, or no consent link present — treat as no consent.
        }

        return null;
    }
}

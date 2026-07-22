// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Agents.AI;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// End to end RAG integration tests against a hosted agent backed by Azure AI Search.
/// The hosted agent runs the test container with <c>IT_SCENARIO=azure-search-rag</c>, which
/// wires <see cref="TextSearchProvider"/> over a real <c>SearchClient</c> against the
/// pre-seeded Contoso Outdoors index.
/// </summary>
/// <remarks>
/// Each test asks for a unique <c>*-CANARY-*</c> token that exists ONLY in the seeded
/// document. The model cannot fabricate these tokens from its training data, so a passing
/// assertion is proof the agent retrieved the seeded document via Azure AI Search rather
/// than answering from general knowledge.
/// </remarks>
[Trait("Category", "FoundryHostedAgents")]
public sealed class AzureSearchRagHostedAgentTests(AzureSearchRagHostedAgentFixture fixture)
    : IClassFixture<AzureSearchRagHostedAgentFixture>
{
    private readonly AzureSearchRagHostedAgentFixture _fixture = fixture;

    [Fact]
    public async Task RagAnswer_CitesSeededReturnPolicy_WhenAskedAboutReturnsAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act: ask about the canary SKU embedded in the seeded Return Policy doc. The
        // canary token (TR-CANARY-7821) is unfakeable - it does not exist in any model
        // training data, so its presence in the answer is proof the agent retrieved
        // the seeded document via the Azure AI Search adapter.
        var response = await agent.RunAsync(
            "What item code do I get with my return? Cite the source.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("TR-CANARY-7821", response.Text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task RagAnswer_CitesShippingGuide_WhenAskedAboutShippingAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act: canary promo code (SHIP-CANARY-4493) is unique to the seeded Shipping
        // Guide doc. Its presence proves the answer was grounded in retrieved content.
        var response = await agent.RunAsync(
            "What promo code can I use for free overnight shipping? Cite the source.");

        // Assert
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("SHIP-CANARY-4493", response.Text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task RagAnswer_StaysGroundedWithoutContext_WhenAskedUnrelatedQuestionAsync()
    {
        // Arrange: ask something that is NOT covered by the three seeded Contoso documents.
        var agent = this._fixture.Agent;

        // Act
        var response = await agent.RunAsync(
            "What is the boiling point of liquid nitrogen in degrees Celsius? " +
            "Just give the number with units, no other context.");

        // Assert: response is non empty AND does NOT fabricate a Contoso source citation.
        // The agent may either answer from its general knowledge or admit uncertainty; either
        // is acceptable. The key assertion is that we do not see a fake Contoso link.
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.DoesNotContain("contoso.com", response.Text, StringComparison.OrdinalIgnoreCase);
    }
}

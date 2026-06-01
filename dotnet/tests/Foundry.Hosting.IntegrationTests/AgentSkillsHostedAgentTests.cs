// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading.Tasks;
using Foundry.Hosting.IntegrationTests.Fixtures;
using Microsoft.Extensions.AI;

namespace Foundry.Hosting.IntegrationTests;

/// <summary>
/// Integration tests that exercise the Agent Skills pattern in a hosted agent container.
/// The container uses <see cref="Microsoft.Agents.AI.AgentSkillsProvider"/> with two
/// Contoso Outdoors skills (support-style, escalation-policy) to verify the progressive
/// disclosure flow: skills are advertised in the system prompt and loaded on demand via
/// the <c>load_skill</c> tool when the model decides they are relevant.
/// </summary>
[Trait("Category", "FoundryHostedAgents")]
public sealed class AgentSkillsHostedAgentTests(AgentSkillsHostedAgentFixture fixture) : IClassFixture<AgentSkillsHostedAgentFixture>
{
    private readonly AgentSkillsHostedAgentFixture _fixture = fixture;

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task RoutineQuestion_LoadsSupportStyleSkillAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act — ask a routine support question that should trigger the support-style skill
        var response = await agent.RunAsync(
            "Hi, I am Alex. I just want to confirm I can return my tent within 30 days.");

        // Assert — response should contain the canary token proving the skill was loaded
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("STYLE-CANARY-3318", response.Text);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task EscalationTrigger_LoadsEscalationPolicySkillAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act — trigger an escalation (legal threat + refund > $500)
        var response = await agent.RunAsync(
            "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer.");

        // Assert — response should contain the escalation canary token
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("ESC-CANARY-7742", response.Text);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task SkillsAreAdvertised_LoadSkillToolIsAvailableAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act — ask the model what skills are available (triggers system prompt inspection)
        var response = await agent.RunAsync(
            "List the skills you have access to. Just give me their names.");

        // Assert — both skills should be mentioned (they are advertised in the system prompt)
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.Contains("support-style", response.Text);
        Assert.Contains("escalation-policy", response.Text);
    }

    [Fact(Skip = "Pending TestContainer build and end to end smoke (step 5).")]
    public async Task LoadSkill_InvokesToolAndReturnsContentAsync()
    {
        // Arrange
        var agent = this._fixture.Agent;

        // Act — ask a question that should load a specific skill
        var response = await agent.RunAsync(
            "I need to know the escalation policy for customer tickets. Load the escalation-policy skill and tell me the rules.");

        // Assert — the response should reference the load_skill tool invocation
        Assert.False(string.IsNullOrWhiteSpace(response.Text));
        Assert.True(
            response.Messages.Any(m => m.Contents.OfType<FunctionCallContent>().Any(fc => fc.Name == "load_skill")),
            "Expected at least one load_skill FunctionCallContent in the response messages.");
    }
}

// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Base fixture for Foundry Hosted Agent integration tests.
///
/// Each derived fixture represents one scenario (happy path, tool calling, toolbox, etc.) and
/// targets a stable, scenario-keyed agent name (e.g. <c>it-happy-path</c>). The fixture creates
/// a new <see cref="ProjectsAgentVersion"/> on each <see cref="InitializeAsync"/>, polls until
/// active, patches the agent's endpoint to route 100% of traffic to that new version, then
/// exposes the wrapped <see cref="AIAgent"/> for tests via <see cref="Agent"/>.
///
/// On <see cref="DisposeAsync"/> only the version created by this fixture is removed; the agent
/// itself (and therefore its managed identity) is left in place. This is critical because the
/// agent's managed identity must hold <c>Azure AI User</c> on the project scope to serve
/// inbound inference traffic, and that role assignment is lost when the agent itself is deleted.
///
/// Prerequisite: each scenario agent (and its managed identity) must exist and have
/// <c>Azure AI User</c> pre-granted on the project scope before the tests run. See
/// <c>scripts/it-bootstrap-agents.ps1</c>.
///
/// The container image is the same for every scenario; the scenario itself is selected by
/// the <c>IT_SCENARIO</c> environment variable in <see cref="HostedAgentDefinition.EnvironmentVariables"/>,
/// configured by each derived fixture via <see cref="ScenarioName"/>.
/// </summary>
public abstract class HostedAgentFixture : IAsyncLifetime
{
    private const string ScenarioEnvironmentVariable = "IT_SCENARIO";
    private const string RunIdEnvironmentVariable = "IT_RUN_ID";
    private const string FoundryFeaturesHeader = "Foundry-Features";
    private const string HostedAgentsFeatureValue = "HostedAgents=V1Preview";
    private const string EnableVnextExperienceMetadataKey = "enableVnextExperience";

    private AgentAdministrationClient _adminClient = null!;

    /// <summary>
    /// Scenario keyword passed to the container as <c>IT_SCENARIO</c>. Derived fixtures override.
    /// </summary>
    protected abstract string ScenarioName { get; }

    /// <summary>
    /// CPU request for the hosted agent container. Override per scenario if needed.
    /// </summary>
    protected virtual string Cpu => "0.25";

    /// <summary>
    /// Memory request for the hosted agent container. Override per scenario if needed.
    /// </summary>
    protected virtual string Memory => "0.5Gi";

    /// <summary>
    /// Maximum time to wait for <see cref="AgentVersionStatus.Active"/> after creation.
    /// </summary>
    protected virtual TimeSpan ProvisioningTimeout => TimeSpan.FromMinutes(5);

    /// <summary>
    /// The wrapped agent. Available after <see cref="InitializeAsync"/>.
    /// </summary>
    public AIAgent Agent { get; private set; } = null!;

    /// <summary>
    /// The stable, scenario keyed agent name registered in Foundry (e.g. <c>it-happy-path</c>).
    /// The agent itself is provisioned out of band (see <c>scripts/it-bootstrap-agents.ps1</c>);
    /// each test run only adds and removes a version under it.
    /// </summary>
    public string AgentName { get; private set; } = null!;

    /// <summary>
    /// The agent version assigned by Foundry on creation.
    /// </summary>
    public string AgentVersion { get; private set; } = null!;

    /// <summary>
    /// The underlying <see cref="AIProjectClient"/>, useful for tests that need to talk
    /// to the conversations or responses APIs directly (e.g. to assert chain visibility).
    /// </summary>
    public AIProjectClient ProjectClient { get; private set; } = null!;

    /// <summary>
    /// Creates a server side conversation that tests can pass via <c>ChatOptions.ConversationId</c>
    /// to exercise multi turn flows backed by the Foundry conversations service.
    /// </summary>
    public async Task<string> CreateConversationAsync()
    {
        var response = await this.ProjectClient.GetProjectOpenAIClient().GetProjectConversationsClient().CreateProjectConversationAsync().ConfigureAwait(false);
        return response.Value.Id;
    }

    /// <summary>
    /// Deletes a previously created conversation. Used by tests in their cleanup blocks.
    /// </summary>
    public async Task DeleteConversationAsync(string conversationId)
    {
        try
        {
            await this.ProjectClient.GetProjectOpenAIClient().GetProjectConversationsClient().DeleteConversationAsync(conversationId).ConfigureAwait(false);
        }
        catch
        {
            // Best effort cleanup mirroring DisposeAsync.
        }
    }

    /// <summary>
    /// Counts items currently stored in a conversation. Used by tests verifying that a
    /// <c>stored=false</c> request did not append to the conversation.
    /// </summary>
    public async Task<int> CountConversationItemsAsync(string conversationId)
    {
        var count = 0;
        await foreach (var _ in this.ProjectClient.GetProjectOpenAIClient().GetProjectConversationsClient().GetProjectConversationItemsAsync(conversationId, order: "asc").ConfigureAwait(false))
        {
            count++;
        }

        return count;
    }

    public async ValueTask InitializeAsync()
    {
        var endpoint = new Uri(TestConfiguration.GetRequiredValue(TestSettings.AzureAIProjectEndpoint));
        var image = TestConfiguration.GetRequiredValue(TestSettings.FoundryHostingItImage);

        var credential = TestAzureCliCredentials.CreateAzureCliCredential();

        var adminOptions = new AgentAdministrationClientOptions();
        adminOptions.AddPolicy(new FoundryFeaturesPolicy(HostedAgentsFeatureValue), PipelinePosition.PerCall);
        this._adminClient = new AgentAdministrationClient(endpoint, credential, adminOptions);
        this.ProjectClient = new AIProjectClient(endpoint, credential);

        this.AgentName = $"it-{this.ScenarioName}";

        var definition = new HostedAgentDefinition(cpu: this.Cpu, memory: this.Memory)
        {
            Image = image,
        };
        definition.Versions.Add(new ProtocolVersionRecord(ProjectsAgentProtocol.Responses, "1.0.0"));
        definition.EnvironmentVariables[ScenarioEnvironmentVariable] = this.ScenarioName;
        // Foundry deduplicates versions by content hash, so a fixture re-using the same
        // definition would just receive the bootstrap version and then delete it on dispose.
        // Adding a per-run env var forces a brand new version that the dispose can safely remove
        // without touching the bootstrap version (which keeps the agent alive across runs).
        definition.EnvironmentVariables[RunIdEnvironmentVariable] = Guid.NewGuid().ToString("N");

        // Allow derived fixtures to layer additional environment variables before submission.
        this.ConfigureEnvironment(definition.EnvironmentVariables);

        var creationOptions = new ProjectsAgentVersionCreationOptions(definition);
        creationOptions.Metadata[EnableVnextExperienceMetadataKey] = "true";

        // Adds a new version under the (stable) agent name. Auto-creates the agent on first run.
        // The agent is intentionally never deleted because its managed identity must hold the
        // pre-granted role assignment for inbound inference to succeed (see class docs).
        var version = await this._adminClient.CreateAgentVersionAsync(this.AgentName, creationOptions).ConfigureAwait(false);
        var activeVersion = await WaitForActiveAsync(this._adminClient, version.Value, this.ProvisioningTimeout).ConfigureAwait(false);
        this.AgentVersion = activeVersion.Version;

        // The agent endpoint must already be configured to route via @latest. The bootstrap
        // script (scripts/it-bootstrap-agents.ps1) does that one-time per agent. Each new
        // version we create automatically becomes the served one because @latest resolves
        // to the highest version number.
        //
        // Build a per-agent ProjectOpenAIClient (the cached projectClient.ProjectOpenAIClient is bound
        // to the project-level URL and cannot serve a hosted agent). AgentName on the options selects
        // the per-agent URL suffix `/agents/{name}/endpoint/protocols/openai`. The Foundry-Features
        // header is also required on the invocation pipeline (not just the admin one) for hosted agents.
        var openAIOptions = new ProjectOpenAIClientOptions { AgentName = this.AgentName };
        openAIOptions.AddPolicy(new FoundryFeaturesPolicy(HostedAgentsFeatureValue), PipelinePosition.PerCall);
        var openAIClient = new ProjectOpenAIClient(endpoint, credential, openAIOptions);
        var responsesClient = openAIClient.GetProjectResponsesClient();

        this.Agent = responsesClient.AsIChatClient().AsAIAgent(name: this.AgentName);
    }

    public async ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);

        if (this._adminClient is null || this.AgentName is null || this.AgentVersion is null)
        {
            return;
        }

        try
        {
            // Delete only the version we created. The agent itself MUST stay so that its
            // managed identity (and the pre-granted Azure AI User role on it) survive across
            // test runs. If we delete the agent, Foundry mints a new MI on the next create
            // and inference fails with PermissionDenied until the role is regranted.
            await this._adminClient.DeleteAgentVersionAsync(this.AgentName, this.AgentVersion).ConfigureAwait(false);
        }
        catch
        {
            // Best effort cleanup. Never throw from DisposeAsync because that would mask
            // the real test failure. Orphan versions accumulate harmlessly; a maintenance
            // script can prune them when needed.
        }
    }

    /// <summary>
    /// Hook for derived fixtures to add scenario specific environment variables.
    /// Reserved names (anything matching <c>FOUNDRY_*</c> or <c>AGENT_*</c>) are forbidden by the platform.
    /// </summary>
    protected virtual void ConfigureEnvironment(IDictionary<string, string> environment)
    {
    }

    private static async Task<ProjectsAgentVersion> WaitForActiveAsync(
        AgentAdministrationClient adminClient,
        ProjectsAgentVersion version,
        TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (version.Status != AgentVersionStatus.Active && version.Status != AgentVersionStatus.Failed)
        {
            if (DateTimeOffset.UtcNow > deadline)
            {
                throw new TimeoutException(
                    $"Hosted agent '{version.Name}' version '{version.Version}' did not become Active within {timeout.TotalSeconds:F0}s. Last status: {version.Status}.");
            }

            await Task.Delay(TimeSpan.FromMilliseconds(500), CancellationToken.None).ConfigureAwait(false);
            version = (await adminClient.GetAgentVersionAsync(version.Name, version.Version).ConfigureAwait(false)).Value;
        }

        if (version.Status != AgentVersionStatus.Active)
        {
            throw new InvalidOperationException(
                $"Hosted agent '{version.Name}' version '{version.Version}' failed to deploy. Status: {version.Status}.");
        }

        return version;
    }

    /// <summary>
    /// Pipeline policy that adds the Foundry feature header on every request.
    /// Required for hosted agent operations until the V1 preview flag is removed.
    /// </summary>
    private sealed class FoundryFeaturesPolicy(string features) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.SetHeader(message);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.SetHeader(message);
            await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
        }

        private void SetHeader(PipelineMessage message)
        {
            // Set rather than Add to avoid duplicate headers if the pipeline reprocesses
            // the request (retries) or if multiple policies attempt to set the same key.
            message.Request.Headers.Remove(FoundryFeaturesHeader);
            message.Request.Headers.Add(FoundryFeaturesHeader, features);
        }
    }
}

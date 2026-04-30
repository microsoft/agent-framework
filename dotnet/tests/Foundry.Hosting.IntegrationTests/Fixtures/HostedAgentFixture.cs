// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ClientModel.Primitives;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Shared.IntegrationTests;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Base fixture for Foundry Hosted Agent integration tests.
///
/// Each derived fixture represents one scenario (happy path, tool calling, toolbox, etc.).
/// On <see cref="InitializeAsync"/> it provisions a real Foundry hosted agent pointing at
/// the test container image (built and pushed out of band by <c>scripts/it-build-image.ps1</c>),
/// polls until it reports <see cref="AgentVersionStatus.Active"/>, then exposes the wrapped
/// <see cref="AIAgent"/> for tests via <see cref="Agent"/>.
///
/// On <see cref="DisposeAsync"/> it deletes the agent version. Failures during cleanup are
/// swallowed so that a deletion error does not mask a test failure.
///
/// The container image is the same for every scenario; the scenario itself is selected by
/// the <c>IT_SCENARIO</c> environment variable in <see cref="HostedAgentDefinition.EnvironmentVariables"/>,
/// configured by each derived fixture via <see cref="ScenarioName"/>.
/// </summary>
public abstract class HostedAgentFixture : IAsyncLifetime
{
    private const string ScenarioEnvironmentVariable = "IT_SCENARIO";
    private const string FoundryFeaturesHeader = "Foundry-Features";
    private const string HostedAgentsFeatureValue = "HostedAgents=V1Preview";
    private const string EnableVnextExperienceMetadataKey = "enableVnextExperience";

    private AgentAdministrationClient _adminClient = null!;
    private AIProjectClient _projectClient = null!;
    private string _agentName = null!;
    private string _agentVersion = null!;
    private FoundryAgent _agent = null!;

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
    /// The wrapped <see cref="FoundryAgent"/>. Available after <see cref="InitializeAsync"/>.
    /// </summary>
    public FoundryAgent Agent => this._agent;

    /// <summary>
    /// The unique agent name registered in Foundry (e.g. <c>it-happy-path-a1b2c3d4</c>).
    /// </summary>
    public string AgentName => this._agentName;

    /// <summary>
    /// The agent version assigned by Foundry on creation.
    /// </summary>
    public string AgentVersion => this._agentVersion;

    /// <summary>
    /// The underlying <see cref="AIProjectClient"/>, useful for tests that need to talk
    /// to the conversations or responses APIs directly (e.g. to assert chain visibility).
    /// </summary>
    public AIProjectClient ProjectClient => this._projectClient;

    /// <summary>
    /// Creates a server side conversation that tests can pass via <c>ChatOptions.ConversationId</c>
    /// to exercise multi turn flows backed by the Foundry conversations service.
    /// </summary>
    public async Task<string> CreateConversationAsync()
    {
        var response = await this._projectClient.GetProjectOpenAIClient().GetProjectConversationsClient().CreateProjectConversationAsync().ConfigureAwait(false);
        return response.Value.Id;
    }

    /// <summary>
    /// Deletes a previously created conversation. Used by tests in their cleanup blocks.
    /// </summary>
    public async Task DeleteConversationAsync(string conversationId)
    {
        try
        {
            await this._projectClient.GetProjectOpenAIClient().GetProjectConversationsClient().DeleteConversationAsync(conversationId).ConfigureAwait(false);
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
        await foreach (var _ in this._projectClient.GetProjectOpenAIClient().GetProjectConversationsClient().GetProjectConversationItemsAsync(conversationId, order: "asc").ConfigureAwait(false))
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
        this._projectClient = new AIProjectClient(endpoint, credential);

        this._agentName = GenerateUniqueAgentName(this.ScenarioName);

        var definition = new HostedAgentDefinition(cpu: this.Cpu, memory: this.Memory)
        {
            Image = image,
        };
        definition.ProtocolVersions.Add(new ProtocolVersionRecord(ProjectsAgentProtocol.Responses, "1.0.0"));
        definition.EnvironmentVariables[ScenarioEnvironmentVariable] = this.ScenarioName;

        // Allow derived fixtures to layer additional environment variables before submission.
        this.ConfigureEnvironment(definition.EnvironmentVariables);

        var creationOptions = new ProjectsAgentVersionCreationOptions(definition);
        creationOptions.Metadata[EnableVnextExperienceMetadataKey] = "true";

        var version = await this._adminClient.CreateAgentVersionAsync(this._agentName, creationOptions).ConfigureAwait(false);
        var activeVersion = await WaitForActiveAsync(this._adminClient, version.Value, this.ProvisioningTimeout).ConfigureAwait(false);
        this._agentVersion = activeVersion.Version;

        var record = await this._adminClient.GetAgentAsync(this._agentName).ConfigureAwait(false);
        this._agent = this._projectClient.AsAIAgent(record.Value);
    }

    public async ValueTask DisposeAsync()
    {
        GC.SuppressFinalize(this);

        if (this._adminClient is null || this._agentName is null)
        {
            return;
        }

        try
        {
            await this._adminClient.DeleteAgentAsync(this._agentName).ConfigureAwait(false);
        }
        catch
        {
            // Best effort cleanup. Never throw from DisposeAsync because that would mask
            // the real test failure, and orphaned agents can be reaped by a separate
            // maintenance script.
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

    private static string GenerateUniqueAgentName(string scenario) =>
        $"it-{scenario}-{Guid.NewGuid().ToString("N").Substring(0, 8)}";

    /// <summary>
    /// Pipeline policy that adds the Foundry feature header on every request.
    /// Required for hosted agent operations until the V1 preview flag is removed.
    /// </summary>
    private sealed class FoundryFeaturesPolicy(string features) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            SetHeader(message);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            SetHeader(message);
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

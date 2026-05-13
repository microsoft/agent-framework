// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using AgentConformance.IntegrationTests.Support;
using Shared.IntegrationTests;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=azure-search-rag</c> mode.
/// Wires the container up with an Azure AI Search backed <see cref="Microsoft.Agents.AI.TextSearchProvider"/>
/// adapter that retrieves Contoso Outdoors documents from a pre-provisioned search index before each
/// model invocation.
/// </summary>
/// <remarks>
/// Prerequisites managed out of band:
/// <list type="bullet">
///   <item><description>The <c>it-azure-search-rag</c> agent's managed identity must hold
///   <c>Search Index Data Reader</c> on the search service scope. Granted manually after
///   the first <c>scripts/it-bootstrap-agents.ps1</c> run; see the IT README.</description></item>
///   <item><description>The search index referenced by <c>AZURE_SEARCH_INDEX_NAME</c> must
///   already exist with the documented schema and Contoso Outdoors content. The search
///   service is shared with <c>python-sample-validation.yml</c>; no .NET-side provisioning
///   script ships with this repository.</description></item>
/// </list>
/// </remarks>
public sealed class AzureSearchRagHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "azure-search-rag";

    /// <summary>
    /// Inject the AZURE_SEARCH_* env vars onto the hosted agent definition so the test container
    /// scenario branch can construct its <c>SearchClient</c>. These names are NOT in the platform
    /// reserved <c>FOUNDRY_*</c> / <c>AGENT_*</c> namespace so they are safe to set.
    /// </summary>
    protected override void ConfigureEnvironment(IDictionary<string, string> environment)
    {
        environment[TestSettings.AzureSearchEndpoint] = TestConfiguration.GetRequiredValue(TestSettings.AzureSearchEndpoint);
        environment[TestSettings.AzureSearchIndexName] = TestConfiguration.GetRequiredValue(TestSettings.AzureSearchIndexName);
    }
}

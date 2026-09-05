// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using AgentConformance.IntegrationTests.Support;
using Shared.IntegrationTests;

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that uses the Foundry Azure AI Search hosted tool and exposes its
/// citations through the hosted Responses API.
/// </summary>
public sealed class AzureSearchToolAnnotationsHostedAgentFixture : HostedAgentFixture
{
    private const string DefaultConnectionName = "azure-ai-search-contoso";

    protected override string ScenarioName => "azure-search-tool-annotations";

    protected override void ConfigureEnvironment(IDictionary<string, string> environment)
    {
        var connectionName =
            TestConfiguration.GetValue(TestSettings.AzureSearchConnectionName) ??
            DefaultConnectionName;
        environment[TestSettings.AzureSearchConnectionId] =
            this.ProjectClient.Connections.GetConnection(connectionName).Value.Id;
        environment[TestSettings.AzureSearchIndexName] =
            TestConfiguration.GetRequiredValue(TestSettings.AzureSearchIndexName);
    }
}

// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that uses <see cref="Microsoft.Extensions.AI.HostedWebSearchTool"/>
/// and exposes its output through the hosted Responses API.
/// </summary>
public sealed class WebSearchAnnotationsHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "web-search-annotations";
}

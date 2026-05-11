// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=custom-storage</c> mode.
/// The container substitutes the default Responses storage provider with a custom in memory
/// implementation so tests can verify that conversation history is read from and written to
/// the custom store rather than the platform default.
/// </summary>
public sealed class CustomStorageHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "custom-storage";
}

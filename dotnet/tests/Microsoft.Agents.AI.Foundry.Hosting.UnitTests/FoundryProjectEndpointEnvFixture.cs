// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// xUnit collection that serializes tests mutating the <c>FOUNDRY_PROJECT_ENDPOINT</c>
/// process environment variable. Without this, parallel test execution causes flaky
/// races between tests that set / unset the variable.
/// </summary>
[CollectionDefinition(Name, DisableParallelization = true)]
public sealed class FoundryProjectEndpointEnvFixture
{
    public const string Name = "FoundryProjectEndpointEnv";
}

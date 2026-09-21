// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a hosted agent that runs the test container in <c>IT_SCENARIO=user-identity</c> mode.
/// The container echoes the platform user isolation key so client tests can assert that
/// <c>x-ms-user-identity</c> produces distinct effective users on the same hosted session.
/// </summary>
public sealed class UserIdentityHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "user-identity";
}

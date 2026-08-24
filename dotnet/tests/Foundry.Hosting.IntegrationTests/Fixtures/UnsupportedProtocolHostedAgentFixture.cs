// Copyright (c) Microsoft. All rights reserved.

namespace Foundry.Hosting.IntegrationTests.Fixtures;

/// <summary>
/// Provisions a dedicated <c>it-unsupported-protocol</c> agent under the legacy responses protocol
/// <c>1.0.0</c> on purpose. The test container targets protocol <c>2.0.0</c> only, so a request served
/// as <c>1.0.0</c> (no <c>x-agent-foundry-call-id</c> header) must fail fast with a clear <c>501</c>
/// rather than an opaque 500. A dedicated agent name keeps this 1.0.0 deployment isolated from the
/// 2.0.0 scenario agents (notably <c>it-happy-path</c>), whose <c>@latest</c> must stay 2.0.0.
/// See <see cref="UnsupportedProtocolHostedAgentTests"/>.
/// </summary>
public sealed class UnsupportedProtocolHostedAgentFixture : HostedAgentFixture
{
    protected override string ScenarioName => "unsupported-protocol";

    protected override string ResponsesProtocolVersion => "1.0.0";
}

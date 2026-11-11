// Copyright (c) Microsoft. All rights reserved.


namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Status of <see cref="FoundryToolboxService"/> startup, used by the
/// <c>foundry-toolbox</c> health check on the <c>GET /readiness</c> probe.
/// Startup only resolves configuration; toolboxes are opened for each response, so a healthy
/// toolbox check does not mean that a toolbox is reachable or usable by a particular caller.
/// </summary>
internal enum FoundryToolboxStartupStatus
{
    /// <summary>
    /// <see cref="FoundryToolboxService.StartAsync"/> has not completed. If checked in this state,
    /// the toolbox health check reports its registration's failure status
    /// (<c>Unhealthy</c> by default). An exception that escapes startup leaves this status unchanged.
    /// </summary>
    Pending = 0,

    /// <summary>
    /// Startup resolved the project endpoint and validated the configured toolbox names, or no
    /// toolbox names were configured. The health check reports <c>Healthy</c>.
    /// </summary>
    Healthy = 1,

    /// <summary>
    /// No project endpoint was resolved from the configured override or the
    /// <c>FOUNDRY_PROJECT_ENDPOINT</c> and <c>AZURE_AI_PROJECT_ENDPOINT</c> environment variables.
    /// Toolbox support is disabled. This is normal for local <c>dotnet run</c> flows,
    /// and the toolbox health check reports <c>Healthy</c>.
    /// </summary>
    NoEndpoint = 3,
}

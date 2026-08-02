// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Hosting;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// Routing helpers for contributor samples that host a Foundry-managed agent locally.
/// </summary>
public static class HostedContributorRouteExtensions
{
    /// <summary>
    /// In Development, maps the per-agent OpenAI route shape that live Foundry uses
    /// (<c>/api/projects/{project}/agents/{agentName}/endpoint/protocols/openai/responses</c>) on top
    /// of the default <c>MapFoundryResponses()</c> so a local REPL client can reach the agent through
    /// <c>AIProjectClient.AsAIAgent(Uri agentEndpoint)</c>, which is the only supported consumption path
    /// for Foundry-hosted agents.
    ///
    /// <para>
    /// The <c>{project}</c> and <c>{agentName}</c> segments are route-parameter wildcards on the server
    /// side; the handler does not consume them, so any value sent by the client is accepted.
    /// </para>
    ///
    /// <para><b>For local contributor debugging only and should not be used in production.</b></para>
    /// </summary>
    /// <param name="app">The <see cref="WebApplication"/> to attach the routes to.</param>
    /// <returns>The same <see cref="WebApplication"/> for chaining.</returns>
    public static WebApplication MapDevTemporaryLocalAgentEndpoint(this WebApplication app)
    {
        ArgumentNullException.ThrowIfNull(app);

        if (app.Environment.IsDevelopment())
        {
            app.MapFoundryResponses("api/projects/{project}/agents/{agentName}/endpoint/protocols/openai");
        }

        return app;
    }
}

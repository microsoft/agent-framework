// Copyright (c) Microsoft. All rights reserved.

using AGUI.Abstractions;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Configures the ASP.NET Core <see cref="JsonOptions"/> used to (de)serialize AG-UI requests and
/// responses so that the AG-UI wire types and the Agent Framework abstractions are resolvable.
/// </summary>
internal sealed class ConfigureAGUIJsonOptions : IConfigureOptions<JsonOptions>
{
    public void Configure(JsonOptions options)
    {
        var chain = options.SerializerOptions.TypeInfoResolverChain;

        // Both resolvers must go in front of the reflection-based resolver ASP.NET Core already
        // placed at the head of the chain; appending leaves them unreachable for every type that
        // reflection can handle, which silently discards the AG-UI wire-format rules.
        //
        // AGUIJsonUtilities.DefaultTypeInfoResolver is the AG-UI context plus the modifier that omits
        // properties with no value. Without it the SSE events go out with explicit nulls for their
        // optional fields ("parentRunId": null and similar), which receiving SDKs reject. The AG-UI
        // resolver is needed on the net10 TypedResults.ServerSentEvents path, which serializes events
        // through the configured ASP.NET Core JsonSerializerOptions.
        //
        // Agent Framework abstractions follow so that M.E.AI types are handled via its resolver.
        chain.Insert(0, AGUIJsonUtilities.DefaultTypeInfoResolver);
        chain.Insert(1, AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
    }
}

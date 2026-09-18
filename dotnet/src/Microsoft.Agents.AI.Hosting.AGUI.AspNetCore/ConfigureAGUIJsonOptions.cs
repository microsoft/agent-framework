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

        // Agent Framework abstractions first to ensure M.E.AI types are handled via its resolver,
        // followed by the AG-UI wire-format resolver for protocol types (the AG-UI context is needed
        // on the net10 TypedResults.ServerSentEvents path, which serializes events through the
        // configured ASP.NET Core JsonSerializerOptions).
        chain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        chain.Add(AGUIJsonSerializerContext.Default.Options.TypeInfoResolver!);
    }
}

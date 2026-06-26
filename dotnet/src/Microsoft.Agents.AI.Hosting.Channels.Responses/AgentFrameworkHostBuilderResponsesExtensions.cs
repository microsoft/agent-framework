// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>
/// Extensions on <see cref="IAgentFrameworkHostBuilder"/> for the OpenAI Responses channel.
/// </summary>
public static class AgentFrameworkHostBuilderResponsesExtensions
{
    /// <summary>Add the OpenAI Responses-shaped channel.</summary>
    public static IAgentFrameworkHostBuilder AddResponsesChannel(
        this IAgentFrameworkHostBuilder builder,
        Action<ResponsesChannelOptions>? configure = null)
    {
        Throw.IfNull(builder);
        var options = new ResponsesChannelOptions();
        configure?.Invoke(options);
        return builder.AddChannel(new ResponsesChannel(options));
    }
}

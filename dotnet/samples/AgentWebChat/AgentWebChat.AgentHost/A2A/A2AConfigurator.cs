// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents.A2A;

namespace AgentWebChat.AgentHost.A2A;

internal static class A2AConfigurator
{
    public static void ConfigureA2A(WebApplication app)
    {
        var a2aConnector = app.BuildA2AConnector();

        app.AttachHttpA2A(
            a2aConnector: a2aConnector,
            taskStore: null,
            path: "/a2a");
    }

#pragma warning disable CA1859 // Use concrete types when possible for improved performance
    private static IA2AConnector BuildA2AConnector(this WebApplication _)
#pragma warning restore CA1859 // Use concrete types when possible for improved performance
    {
        return new AgentSelectorConnector();
    }
}

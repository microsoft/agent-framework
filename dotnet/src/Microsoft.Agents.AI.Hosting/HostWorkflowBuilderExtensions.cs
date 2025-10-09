// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// todo
/// </summary>
public static class HostWorkflowBuilderExtensions
{
    /// <summary>
    /// todo
    /// </summary>
    /// <param name="builder"></param>
    /// <param name="name"></param>
    /// <returns></returns>
    public static IHostAgentBuilder AsAIAgent(this IHostWorkflowBuilder builder, string? name = null)
    {
        var agentName = name ?? builder.Name;
        return builder.HostApplicationBuilder.AddAIAgent(agentName, (sp, key) =>
        {
            var workflow = sp.GetRequiredKeyedService<Workflow>(key);
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
            return workflow.AsAgentAsync(name: key).AsTask().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits
        });
    }
}

// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Extensions.DependencyInjection;

public static class ServiceCollections
{
    public static void AddDevUI(this IServiceCollection services)
    {
        services.AddSingleton<RegisteredAgentsProvider>(sp =>
        {
            return new(sp, services);
        });
    }
}

internal class RegisteredAgentsProvider
{
    private readonly IServiceProvider _serviceProvider;
    private readonly IServiceCollection _services;

    public RegisteredAgentsProvider(IServiceProvider serviceProvider, IServiceCollection services)
    {
        this._serviceProvider = serviceProvider;
        this._services = services;
    }

    public List<AIAgent> ResolveAgents()
    {
        var agentsMap = this._serviceProvider.GetKeyedServices<AIAgent>(KeyedService.AnyKey)
            .ToDictionary(x => x.DisplayName);

        var workflows = this._serviceProvider.GetKeyedServices<Workflow>(KeyedService.AnyKey);
        var workflowsAsAgents = workflows.Select(x => x.AsAgent(name: x.Name));
        foreach (var workflowAsAgent in workflowsAsAgents.Where(w => w.Name is not null))
        {
            agentsMap.TryAdd(workflowAsAgent.Name!, workflowAsAgent);
        }

        return agentsMap.Values.ToList();
    }
}

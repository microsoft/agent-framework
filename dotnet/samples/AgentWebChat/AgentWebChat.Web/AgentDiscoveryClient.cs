// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.Hosting;

namespace AgentWebChat.Web;

public class AgentDiscoveryClient(HttpClient httpClient, ILogger<AgentDiscoveryClient> logger)
{
    public async Task<List<AgentDiscoveryCard>> GetAgentsAsync(CancellationToken cancellationToken = default)
    {
        var response = await httpClient.GetAsync(new Uri("/agents", UriKind.Relative), cancellationToken);
        response.EnsureSuccessStatusCode();

        var json = await response.Content.ReadAsStringAsync(cancellationToken);
        var agents = JsonSerializer.Deserialize<List<AgentDiscoveryCard>>(json, AgentHostingJsonUtilities.DefaultOptions) ?? [];

        logger.LogInformation("Retrieved {AgentCount} agents from the API", agents.Count);
        _ = new HttpActorClient(null!);
        return agents;
    }

    public class AgentDiscoveryCard
    {
        public string? Name { get; set; }
        public string? Description { get; set; }
    }
}

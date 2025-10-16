using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

using Microsoft.Agents.AI.Hosting.Converters;
using Azure.AI.AgentsHosting.Ingress.Invocation;
using Azure.AI.AgentsHosting.Ingress.Invocation.Stream;

using AzureAIAgents.Models;

using Microsoft.Agents.AI;
using Microsoft.Extensions.Logging;

namespace Azure.AI.AgentsHosting.AgentFramework;

public class AfInvocation(AIAgent agent, ILogger<AfInvocation> logger) : AgentInvocationBase
{
    protected override async Task<AzureAIAgents.Models.Response> DoInvokeAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken)
    {
        Activity.Current?.SetServiceNamespace("agentframework");

        var messages = createResponse.GetInputMessages();
        var response = await agent.RunAsync(messages, cancellationToken: cancellationToken).ConfigureAwait(false);
        return response.ToResponse(createResponse, context);
    }

    protected override INestedStreamEventGenerator<AzureAIAgents.Models.Response> DoInvokeStreamAsync(CreateResponse createResponse,
        AgentInvocationContext context,
        CancellationToken cancellationToken)
    {
        Activity.Current?.SetServiceNamespace("agentframework");

        var messages = createResponse.GetInputMessages();
        var updates = agent.RunStreamingAsync(messages, cancellationToken: cancellationToken);
        // TODO refine to multicast event
        IList<Action<ResponseUsage>> usageUpdaters = [];

        var seq = SequenceNumberFactory.Default;
        return new NestedResponseGenerator()
        {
            ResponseId = context.ResponseId,
            ConversationId = context.ConversationId,
            Request = createResponse,
            Seq = seq,
            CancellationToken = cancellationToken,
            SubscribeUsageUpdate = usageUpdaters.Add,
            OutputGenerator = new AfItemResourceGenerator()
            {
                Context = context,
                NotifyOnUsageUpdate = usage =>
                {
                    foreach (var updater in usageUpdaters)
                    {
                        updater(usage);
                    }
                },
                Updates = updates,
                Seq = seq,
                CancellationToken = cancellationToken,
            }
        };
    }
}

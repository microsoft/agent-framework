// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Specialized;

internal class AIAgentHostExecutor : ReflectingExecutor<AIAgentHostExecutor>, IMessageHandler<IList<ChatMessage>>
{
    private AIAgent Agent { get; set; }

    public AIAgentHostExecutor(AIAgent agent)
    {
        this.Agent = agent;
    }

    public async ValueTask HandleAsync(IList<ChatMessage> message, IWorkflowContext context)
    {
        IReadOnlyCollection<ChatMessage> messageList = (message as List<ChatMessage> ?? message.ToList()).AsReadOnly();

        // TODO: Ideally we want to be able to split the Run across multiple super-steps so that we can stream out
        // incremental updates from the chat model. 
        AgentRunResponse runResponse = await this.Agent.RunAsync(messageList).ConfigureAwait(false);

        await context.AddEventAsync(new AgentRunEvent(this.Id, runResponse)).ConfigureAwait(false);
        await context.SendMessageAsync(runResponse).ConfigureAwait(false);
    }
}

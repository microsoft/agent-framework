// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Invocations;
using Microsoft.Agents.AI;

namespace HostedInvocationsEchoAgent;

/// <summary>
/// An <see cref="InvocationHandler"/> that reads the request body as plain text,
/// passes it to the <see cref="EchoAIAgent"/>, and writes the response back.
/// </summary>
public sealed class EchoInvocationHandler(EchoAIAgent agent) : InvocationHandler
{
    /// <inheritdoc/>
    public override async Task HandleAsync(
        HttpRequest request,
        HttpResponse response,
        InvocationContext context,
        CancellationToken cancellationToken)
    {
        // Read the raw text from the request body.
        using var reader = new StreamReader(request.Body);
        var input = await reader.ReadToEndAsync(cancellationToken);

        // Run the echo agent with the input text.
        var agentResponse = await agent.RunAsync(input, cancellationToken: cancellationToken);

        // Write the agent response text back to the HTTP response.
        response.ContentType = "text/plain";
        await response.WriteAsync(agentResponse.Text, cancellationToken);
    }
}

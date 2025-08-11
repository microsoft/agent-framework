// Copyright (c) Microsoft. All rights reserved.

#if NET

using Azure.Identity;
using Microsoft.Agents.Orchestration;
using Microsoft.Agents.Workflows.Core;
using Microsoft.Agents.Workflows.Declarative;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Shared.Diagnostics;
using Microsoft.Shared.Samples;

namespace Workflows;

/// <summary>
/// Demonstrates how to use the <see cref="ConcurrentOrchestration"/>
/// for executing multiple agents on the same task in parallel.
/// </summary>
public class Workflows_Declarative(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Theory]
    [InlineData("deepResearch")]
    [InlineData("demo250729")]
    [InlineData("testChat")]
    [InlineData("testCondition")]
    [InlineData("testEnd")]
    [InlineData("testExpression")]
    [InlineData("testGoto")]
    [InlineData("testLoop")]
    [InlineData("testLoopBreak")]
    [InlineData("testLoopContinue")]
    [InlineData("testTopic")]
    public async Task RunWorkflow(string fileName)
    {
        //using InterceptHandler customHandler = new();
        //using HttpClient customClient = new(customHandler, disposeHandler: false);

        //const string InputEventId = "question";

        Console.WriteLine("WORKFLOW INIT\n");

        using StreamReader yamlReader = File.OpenText(@$"{nameof(Workflows)}\{fileName}.yaml");
        WorkflowContext workflowContext =
            new()
            {
                //HttpClient = customClient,
                LoggerFactory = this.LoggerFactory,
                ActivityChannel = this.Console,
                ProjectEndpoint = Throw.IfNull(TestConfiguration.AzureAI.Endpoint),
                ProjectCredentials = new AzureCliCredential(),
            };
        Workflow<string> workflow = DeclarativeWorkflowBuilder.Build(yamlReader, "input", workflowContext);

        Console.WriteLine("\nWORKFLOW INVOKE\n");

        LocalRunner<string> runner = new(workflow);
        StreamingRun handle = await runner.StreamAsync("<placeholder>");
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is ExecutorCompleteEvent executorComplete)
            {
                Console.WriteLine($"WORKFLOW EVENT: {executorComplete.Data}");
            }
        }
        Console.WriteLine("\nWORKFLOW DONE");
    }
}

//internal sealed class InterceptHandler : HttpClientHandler
//{
//    private static readonly JsonSerializerOptions s_options = new() { WriteIndented = true };

//    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
//    {
//        // Call the inner handler to process the request and get the response
//        HttpResponseMessage response = await base.SendAsync(request, cancellationToken);

//        // Intercept and modify the response
//        Console.WriteLine($"{request.Method} {request.RequestUri}");
//        if (response.Content != null)
//        {
//            string responseContent;
//            try
//            {
//                JsonDocument responseDocument = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(cancellationToken), cancellationToken: cancellationToken);
//                responseContent = JsonSerializer.Serialize(responseDocument, s_options);
//            }
//            catch (ArgumentException)
//            {
//                responseContent = await response.Content.ReadAsStringAsync(cancellationToken);
//            }
//            catch (JsonException)
//            {
//                responseContent = await response.Content.ReadAsStringAsync(cancellationToken);
//            }
//            response.Content = new StringContent(responseContent);
//            //Console.WriteLine(responseContent); // %%% RAISE EVENT
//        }

//        return response;
//    }
//}

#endif

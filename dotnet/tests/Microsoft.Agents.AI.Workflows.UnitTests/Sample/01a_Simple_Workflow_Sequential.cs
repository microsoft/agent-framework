// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using static Microsoft.Agents.AI.Workflows.Sample.Step1EntryPoint;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step1aEntryPoint
{
    // TODO: Maybe env.CreateRunAsync?
    public static async ValueTask RunAsync(TextWriter writer, IWorkflowExecutionEnvironment environment)
    {
        Run run = await environment.RunAsync(WorkflowInstance, "Hello, World!").ConfigureAwait(false);

        Assert.Equal(RunStatus.Idle, await run.GetStatusAsync());

        foreach (WorkflowEvent evt in run.NewEvents)
        {
            if (evt is ExecutorCompletedEvent executorCompleted)
            {
                writer.WriteLine($"{executorCompleted.ExecutorId}: {executorCompleted.Data}");
            }
        }
    }
}

/*
internal class Example
{
    const string GreeterAgent = nameof(GreeterAgent);
    const string TaskAgent1 = nameof(TaskAgent1);
    const string ErrorAgent = nameof(ErrorAgent);
    public WorkflowBuilder CreateTemplate()
    {
        return new WorkflowBuilder(GreeterAgent)
                .AddEdge(GreeterAgent, TaskAgent1)
                .AddEdge(TaskAgent1, ErrorAgent, condition: (object? message) => message is Exception)
                .WithOutputFrom(TaskAgent1);
    }
    public void BuildWorkflow()
    {
        WorkflowBuilder template = CreateTemplate();

        AIAgent myGreeter = new AIAgentBuilder().Build(); // with id = "GreeterAgent"
        AIAgent myTaskAgent = new AIAgentBuilder().Build(); // with id = "TaskAgent1"
        AIAgent myErrorAgent = new AIAgentBuilder().Build(); // with id = "ErrorAgent"

        template.BindExecutor(myGreeter).BindExecutor(myTaskAgent).BindExecutor(myErrorAgent);

        WorkflowBuilder directBuilder = new WorkflowBuilder(myGreeter)
                .AddEdge(myGreeter, myTaskAgent)
                .AddEdge(myTaskAgent, myErrorAgent, condition: (object? message) => message is Exception)
                .WithOutputFrom(myTaskAgent);

        // TODO: Add Id remapping to BindExecutor()
        //ExecutorBinding myRenamedGreeter = myGreeter.BindAsExecutor(IDataDiscoverer: "NewGreeterAgent")

        string executorPlaceholder = "PLACEHODLER";
        WorkflowBuilder builder = new(executorPlaceholder);

        builder.AddEdge(executorPlaceholder, executorPlaceholder); // Direct Edge, Unconditional
        builder.AddEdge(executorPlaceholder, executorPlaceholder,
                        condition: (string? myString) => myString?.Contains("Hello") is true);

        builder.AddFanOutEdge(executorPlaceholder, [executorPlaceholder]); // FanOut Edge, Simple/Unconditional
        // ~equivalent to foreach (executor in [executor])... builder.AddEdge(...)

        static IEnumerable<int> targetSelector(object? message, int potentialTargetCount) =>
            Enumerable.Range(0, potentialTargetCount);

        builder.AddFanOutEdge(executorPlaceholder, [executorPlaceholder], (Func<object?, int, IEnumerable<int>>)targetSelector);

        builder.AddSwitch(executorPlaceholder,
            (SwitchBuilder sb) =>
                sb.AddCase(predicate: (string? s) => s?.Contains("Hello") is true, executorPlaceholder)
                  .WithDefault(executorPlaceholder));
        // FanIn
        builder.AddFanInEdge([executorPlaceholder], executorPlaceholder); // builder.WaitAll([executor], then: executor)
        // TODO: FanIn
        /*
        builder.AddFanInEdge([executor], executor, FanInStrategy);
         FanInStrategy: => views incoming messages and decides whether or not to send anything
                        => potentially aggregates messages / filters them
         //* /

        AIAgent myAgent = new AIAgentBuilder().Build();
        var myAgentExecutor = myAgent.BindAsExecutor();

        Func<string, ValueTask<Executor>> myFactory;
        ExecutorBinding myExecutor = myFactory.BindAsExecutor("PLACEHOLDER"); // TODO: AsExecutorBinding()

        //builder.AddEdge(myAgent, myAgent);
        builder.BindExecutor(myExecutor); // TODO: Lots of "Bind" - better name?
                                          // Needed at all?
    }
}
// */

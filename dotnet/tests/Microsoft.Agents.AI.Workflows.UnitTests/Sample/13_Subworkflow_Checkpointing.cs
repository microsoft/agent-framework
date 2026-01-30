// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Sample;

internal static class Step13EntryPoint
{
    public static Workflow SubworkflowInstance
    {
        get
        {
            OutputMessagesExecutor output = new(new ChatProtocolExecutorOptions() { StringMessageChatRole = ChatRole.User });
            return new WorkflowBuilder(output).WithOutputFrom(output).Build();
        }
    }

    public static Workflow WorkflowInstance
    {
        get
        {
            ExecutorBinding subworkflow = SubworkflowInstance.BindAsExecutor("EchoSubworkflow");
            return new WorkflowBuilder(subworkflow).WithOutputFrom(subworkflow).Build();
        }
    }

    public static async ValueTask<AgentSession> RunAsAgentAsync(TextWriter writer, string input, IWorkflowExecutionEnvironment environment, AgentSession? session)
    {
        AIAgent hostAgent = WorkflowInstance.AsAgent("echo-workflow", "EchoW", executionEnvironment: environment, includeWorkflowOutputsInResponse: true);

        session ??= await hostAgent.GetNewSessionAsync();
        AgentResponse response;
        ResponseContinuationToken? continuationToken = null;
        do
        {
            response = await hostAgent.RunAsync(input, session, new AgentRunOptions { ContinuationToken = continuationToken });
        } while ((continuationToken = response.ContinuationToken) is { });

        foreach (ChatMessage message in response.Messages)
        {
            writer.WriteLine($"{message.AuthorName}: {message.Text}");
        }

        return session;
    }

    public static async ValueTask<CheckpointInfo> RunAsync(TextWriter writer, string input, IWorkflowExecutionEnvironment environment, CheckpointManager checkpointManager, CheckpointInfo? resumeFrom)
    {
        await using Checkpointed<StreamingRun> checkpointed = await BeginAsync();
        StreamingRun run = checkpointed.Run;

        await run.TrySendMessageAsync(new TurnToken());

        CheckpointInfo? lastCheckpoint = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is WorkflowOutputEvent output)
            {
                if (output.Data is List<ChatMessage> messages)
                {
                    foreach (ChatMessage message in messages)
                    {
                        writer.WriteLine($"{output.ExecutorId}: {message.Text}");
                    }
                }
                else
                {
                    Debug.Fail($"Unexpected output type: {(output.Data == null ? "null" : output.Data?.GetType().Name)}");
                }
            }
            else if (evt is SuperStepCompletedEvent stepCompleted)
            {
                lastCheckpoint = stepCompleted.CompletionInfo?.Checkpoint;
            }
        }

        return lastCheckpoint!;

        async ValueTask<Checkpointed<StreamingRun>> BeginAsync()
        {
            if (resumeFrom == null)
            {
                return await environment.StreamAsync(WorkflowInstance, input, checkpointManager);
            }

            Checkpointed<StreamingRun> checkpointed = await environment.ResumeStreamAsync(WorkflowInstance, resumeFrom, checkpointManager);
            await checkpointed.Run.TrySendMessageAsync(input);
            return checkpointed;
        }
    }
}

// Copyright (c) Microsoft. All rights reserved.

namespace VerifySamples;

/// <summary>
/// Defines the expected behavior for each sample in 03-workflows.
/// </summary>
internal static class WorkflowSamples
{
    public static IReadOnlyList<SampleDefinition> All { get; } =
    [
        // ───────────────────────────────────────────────────────────────────
        // _StartHere
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_StartHere_01_Streaming",
            ProjectPath = "samples/03-workflows/_StartHere/01_Streaming",
            RequiredEnvironmentVariables = [],
            IsDeterministic = true,
            MustContain =
            [
                "UppercaseExecutor: HELLO, WORLD!",
                "ReverseTextExecutor: !DLROW ,OLLEH",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_StartHere_02_AgentsInWorkflows",
            ProjectPath = "samples/03-workflows/_StartHere/02_AgentsInWorkflows",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show agent responses from a translation workflow.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_StartHere_03_AgentWorkflowPatterns",
            ProjectPath = "samples/03-workflows/_StartHere/03_AgentWorkflowPatterns",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            Inputs = ["sequential"],
            InputDelayMs = 3000,
            ExpectedOutputDescription =
            [
                "The output should show a sequential workflow pattern with multiple agents executing tasks in order.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_StartHere_04_MultiModelService",
            ProjectPath = "samples/03-workflows/_StartHere/04_MultiModelService",
            RequiredEnvironmentVariables = ["BEDROCK_ACCESS_KEY", "BEDROCK_SECRET_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
            SkipReason = "Requires multiple external provider API keys (Bedrock, Anthropic, OpenAI).",
        },

        new SampleDefinition
        {
            Name = "Workflow_StartHere_05_SubWorkflows",
            ProjectPath = "samples/03-workflows/_StartHere/05_SubWorkflows",
            RequiredEnvironmentVariables = [],
            IsDeterministic = true,
            MustContain =
            [
                "=== Sub-Workflow Demonstration ===",
                "Final Output:",
                "=== Main Workflow Completed ===",
                "Sample Complete: Workflows can be composed hierarchically using sub-workflows",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_StartHere_06_MixedWorkflowAgentsAndExecutors",
            ProjectPath = "samples/03-workflows/_StartHere/06_MixedWorkflowAgentsAndExecutors",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            Inputs = ["What is 2 plus 2?"],
            InputDelayMs = 3000,
            ExpectedOutputDescription =
            [
                "The output should show agents and executors working together to process a user question.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_StartHere_07_WriterCriticWorkflow",
            ProjectPath = "samples/03-workflows/_StartHere/07_WriterCriticWorkflow",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = ["=== Writer-Critic Iteration Workflow ==="],
            ExpectedOutputDescription =
            [
                "The output should show a writer-critic iteration workflow with writer and critic sections.",
                "The critic should either approve or request revisions.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // Agents
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_Agents_CustomAgentExecutors",
            ProjectPath = "samples/03-workflows/Agents/CustomAgentExecutors",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show custom workflow events including slogan generation and feedback.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_Agents_FoundryAgent",
            ProjectPath = "samples/03-workflows/Agents/FoundryAgent",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            SkipReason = "Requires Azure AI Foundry project endpoint.",
        },

        new SampleDefinition
        {
            Name = "Workflow_Agents_GroupChatToolApproval",
            ProjectPath = "samples/03-workflows/Agents/GroupChatToolApproval",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = ["Starting group chat workflow for software deployment..."],
            ExpectedOutputDescription =
            [
                "The output should show a group chat workflow with QA and DevOps agents for software deployment.",
                "There should be approval requests for tool calls.",
                "The workflow should show interaction between QA and DevOps agents toward deployment.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_Agents_WorkflowAsAnAgent",
            ProjectPath = "samples/03-workflows/Agents/WorkflowAsAnAgent",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            Inputs = ["hello", "exit"],
            InputDelayMs = 5000,
            ExpectedOutputDescription =
            [
                "The output should show a conversational workflow responding to the user's hello message.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // Checkpoint
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_Checkpoint_CheckpointAndRehydrate",
            ProjectPath = "samples/03-workflows/Checkpoint/CheckpointAndRehydrate",
            RequiredEnvironmentVariables = [],
            IsDeterministic = true,
            MustContain =
            [
                "Workflow completed with result:",
                "Number of checkpoints created:",
                "Hydrating a new workflow instance from the 6th checkpoint.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_Checkpoint_CheckpointAndResume",
            ProjectPath = "samples/03-workflows/Checkpoint/CheckpointAndResume",
            RequiredEnvironmentVariables = [],
            IsDeterministic = true,
            MustContain =
            [
                "Workflow completed with result:",
                "Number of checkpoints created:",
                "Restoring from the 6th checkpoint.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_Checkpoint_CheckpointWithHumanInTheLoop",
            ProjectPath = "samples/03-workflows/Checkpoint/CheckpointWithHumanInTheLoop",
            RequiredEnvironmentVariables = [],
            Inputs = ["50", "25", "40", "45", "42", "50", "25", "40", "45", "42"],
            InputDelayMs = 1000,
            MustContain = ["found in"],
            ExpectedOutputDescription =
            [
                "The output should show a number guessing game with higher/lower hints that eventually reaches the correct number.",
                "The output should demonstrate checkpoint save and restore behavior.",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // Concurrent
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_Concurrent_Concurrent",
            ProjectPath = "samples/03-workflows/Concurrent/Concurrent",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show results from concurrent agent processing.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_Concurrent_MapReduce",
            ProjectPath = "samples/03-workflows/Concurrent/MapReduce",
            RequiredEnvironmentVariables = [],
            MustContain =
            [
                "=== RUNNING WORKFLOW ===",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // ConditionalEdges
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_ConditionalEdges_01_EdgeCondition",
            ProjectPath = "samples/03-workflows/ConditionalEdges/01_EdgeCondition",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show an email being classified as spam or not spam and processed accordingly.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_ConditionalEdges_02_SwitchCase",
            ProjectPath = "samples/03-workflows/ConditionalEdges/02_SwitchCase",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show an ambiguous email being classified as spam, not spam, or uncertain.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Workflow_ConditionalEdges_03_MultiSelection",
            ProjectPath = "samples/03-workflows/ConditionalEdges/03_MultiSelection",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show an email being classified and potentially routed to multiple handlers.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // HumanInTheLoop
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_HumanInTheLoop_Basic",
            ProjectPath = "samples/03-workflows/HumanInTheLoop/HumanInTheLoopBasic",
            RequiredEnvironmentVariables = [],
            Inputs = ["50", "25", "40", "45", "42"],
            InputDelayMs = 1000,
            MustContain = ["found in"],
            ExpectedOutputDescription =
            [
                "The output should show a number guessing game with higher/lower hints that eventually reaches the correct number 42.",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // Loop
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_Loop",
            ProjectPath = "samples/03-workflows/Loop",
            RequiredEnvironmentVariables = [],
            MustContain = ["Result:"],
        },

        // ───────────────────────────────────────────────────────────────────
        // SharedStates
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_SharedStates",
            ProjectPath = "samples/03-workflows/SharedStates",
            RequiredEnvironmentVariables = [],
            IsDeterministic = true,
            MustContain =
            [
                "Total Paragraphs:",
                "Total Words:",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // Visualization
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_Visualization",
            ProjectPath = "samples/03-workflows/Visualization",
            RequiredEnvironmentVariables = [],
            IsDeterministic = true,
            MustContain =
            [
                "Generating workflow visualization...",
                "Mermaid string:",
                "DiGraph string:",
            ],
        },

        // ───────────────────────────────────────────────────────────────────
        // Observability
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_Observability_ApplicationInsights",
            ProjectPath = "samples/03-workflows/Observability/ApplicationInsights",
            RequiredEnvironmentVariables = ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
            SkipReason = "Requires Application Insights connection string.",
        },

        new SampleDefinition
        {
            Name = "Workflow_Observability_AspireDashboard",
            ProjectPath = "samples/03-workflows/Observability/AspireDashboard",
            RequiredEnvironmentVariables = [],
            SkipReason = "Requires Aspire Dashboard / OTLP endpoint.",
        },

        new SampleDefinition
        {
            Name = "Workflow_Observability_WorkflowAsAnAgent",
            ProjectPath = "samples/03-workflows/Observability/WorkflowAsAnAgent",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "Interactive console with ReadLine loop; requires OTLP endpoint.",
        },

        // ───────────────────────────────────────────────────────────────────
        // Declarative
        // ───────────────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Workflow_Declarative_ConfirmInput",
            ProjectPath = "samples/03-workflows/Declarative/ConfirmInput",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            Inputs = ["hello", "hello"],
            InputDelayMs = 8000,
            ExpectedOutputDescription = ["The output should show a confirmation prompt and a user response."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_CustomerSupport",
            ProjectPath = "samples/03-workflows/Declarative/CustomerSupport",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["My laptop won't start"],
            InputDelayMs = 3000,
            ExpectedOutputDescription = ["The output should show a customer support workflow processing a laptop issue, with agent responses providing troubleshooting or support."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_DeepResearch",
            ProjectPath = "samples/03-workflows/Declarative/DeepResearch",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            SkipReason = "Requires external weather API (wttr.in).",
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_ExecuteCode",
            ProjectPath = "samples/03-workflows/Declarative/ExecuteCode",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            Inputs = ["What is 12 * 34?"],
            InputDelayMs = 5000,
            ExpectedOutputDescription = ["The output should show a declarative workflow executing generated code, processing a math question and producing a result."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_ExecuteWorkflow",
            ProjectPath = "samples/03-workflows/Declarative/ExecuteWorkflow",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            SkipReason = "Requires a workflow file path as a CLI argument.",
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_FunctionTools",
            ProjectPath = "samples/03-workflows/Declarative/FunctionTools",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["What are today's specials?", "EXIT"],
            InputDelayMs = 8000,
            ExpectedOutputDescription = ["The output should show a workflow calling function tools (e.g. a menu plugin) to answer a question about restaurant specials."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_GenerateCode",
            ProjectPath = "samples/03-workflows/Declarative/GenerateCode",
            IsDeterministic = true,
            MustContain = ["WORKFLOW: Parsing", "WORKFLOW: Defined"],
            ExpectedOutputDescription = ["The output should show a YAML workflow being parsed and C# code being generated from it."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_HostedWorkflow",
            ProjectPath = "samples/03-workflows/Declarative/HostedWorkflow",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            SkipReason = "Hosts a persistent workflow server that does not exit.",
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_InputArguments",
            ProjectPath = "samples/03-workflows/Declarative/InputArguments",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["I'd like to visit Seattle", "EXIT"],
            InputDelayMs = 8000,
            ExpectedOutputDescription = ["The output should show a workflow capturing location input and providing travel-related information about Seattle."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_InvokeFunctionTool",
            ProjectPath = "samples/03-workflows/Declarative/InvokeFunctionTool",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["What's the soup of the day?", "EXIT"],
            InputDelayMs = 8000,
            ExpectedOutputDescription = ["The output should show a workflow invoking a function tool (e.g. a menu plugin) to answer a question about the soup of the day."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_InvokeMcpTool",
            ProjectPath = "samples/03-workflows/Declarative/InvokeMcpTool",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["Search for .NET tutorials on Microsoft Learn"],
            InputDelayMs = 3000,
            ExpectedOutputDescription = ["The output should show a workflow using MCP tools to search Microsoft Learn documentation and provide a summary of results."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_Marketing",
            ProjectPath = "samples/03-workflows/Declarative/Marketing",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["A smart water bottle that tracks hydration"],
            InputDelayMs = 3000,
            ExpectedOutputDescription = ["The output should show a marketing workflow generating content about a smart water bottle product."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_StudentTeacher",
            ProjectPath = "samples/03-workflows/Declarative/StudentTeacher",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["What is 18 + 27?"],
            InputDelayMs = 3000,
            ExpectedOutputDescription = ["The output should show a student-teacher workflow where a student asks a math question and a teacher provides the answer."],
        },

        new SampleDefinition
        {
            Name = "Workflow_Declarative_ToolApproval",
            ProjectPath = "samples/03-workflows/Declarative/ToolApproval",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["Search for .NET tutorials", "EXIT"],
            InputDelayMs = 8000,
            ExpectedOutputDescription = ["The output should show a workflow using an MCP tool with approval to search Microsoft Learn, followed by an exit from the input loop."],
        },
    ];
}

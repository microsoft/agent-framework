// Copyright (c) Microsoft. All rights reserved.

namespace VerifySamples;

/// <summary>
/// Defines the expected behavior for each sample in 02-agents.
/// </summary>
internal static class AgentsSamples
{
    public static IReadOnlyList<SampleDefinition> All { get; } =
    [
        // ── AgentProviders ──────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Agent_With_CustomImplementation",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_CustomImplementation",
            RequiredEnvironmentVariables = [],
            ExpectedOutputDescription =
            [
                "The output should contain uppercased text, because the custom agent converts all text to uppercase.",
                "There should be two outputs — one from a non-streaming call and one from a streaming call.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_AzureOpenAIChatCompletion",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_AzureOpenAIChatCompletion",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_AzureOpenAIResponses",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_AzureOpenAIResponses",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain two separate joke responses about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_AzureAIAgentsPersistent",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_AzureAIAgentsPersistent",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_AzureAIProject",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_AzureAIProject",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            MustContain = ["Latest agent version id:"],
            ExpectedOutputDescription =
            [
                "The output should show a 'Latest agent version id:' line, then joke responses from the agent.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_AzureFoundryModel",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_AzureFoundryModel",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_API_KEY", "AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ── Agents ──────────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Agent_Step01_UsingFunctionToolsWithApprovals",
            ProjectPath = "samples/02-agents/Agents/Agent_Step01_UsingFunctionToolsWithApprovals",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            Inputs = ["Tell me a joke about a pirate", ""],
            InputDelayMs = 5000,
            ExpectedOutputDescription =
            [
                "The output should show the agent responding to user input. The response may be about any topic — jokes, weather, or tool call results are all acceptable.",
                "The output should not contain unhandled exception stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step02_StructuredOutput",
            ProjectPath = "samples/02-agents/Agents/Agent_Step02_StructuredOutput",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain =
            [
                "=== Structured Output with ResponseFormat ===",
                "Assistant Output (JSON):",
                "Assistant Output (Deserialized):",
                "=== Structured Output with RunAsync<T> ===",
                "=== Structured Output with RunStreamingAsync ===",
                "=== Structured Output with UseStructuredOutput Middleware ===",
                "Name:",
            ],
            ExpectedOutputDescription =
            [
                "The output should have four clearly separated sections for different structured output approaches.",
                "The first section should include raw JSON output and then deserialized fields including 'Name:' with a city name.",
                "Each subsequent section should also show 'Name:' followed by a city name.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step03_PersistedConversations",
            ProjectPath = "samples/02-agents/Agents/Agent_Step03_PersistedConversations",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = ["--- Serialized session ---"],
            ExpectedOutputDescription =
            [
                "The output should start with a joke about a pirate.",
                "After the joke there should be a '--- Serialized session ---' separator followed by a JSON block representing the serialized session state.",
                "After the JSON block there should be a second response that retells the same joke in a pirate voice with emojis, demonstrating that context was preserved across serialization.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step04_3rdPartyChatHistoryStorage",
            ProjectPath = "samples/02-agents/Agents/Agent_Step04_3rdPartyChatHistoryStorage",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = ["--- Serialized session ---"],
            ExpectedOutputDescription =
            [
                "The output should contain a pirate joke response and a '--- Serialized session ---' separator with session JSON.",
                "It should show that the session was stored in a vector store, with a 'Session is stored in vector store under key:' line.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step06_DependencyInjection",
            ProjectPath = "samples/02-agents/Agents/Agent_Step06_DependencyInjection",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            Inputs = ["Tell me a joke about a pirate", ""],
            InputDelayMs = 5000,
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate in response to the user's request.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step08_UsingImages",
            ProjectPath = "samples/02-agents/Agents/Agent_Step08_UsingImages",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should describe an image of a nature boardwalk/walkway scene.",
                "It should mention elements like a wooden boardwalk or path, greenery or vegetation, and an outdoor or natural setting.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step09_AsFunctionTool",
            ProjectPath = "samples/02-agents/Agents/Agent_Step09_AsFunctionTool",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should be a response about the weather in Amsterdam, written in French.",
                "The response should reference the tool result: cloudy weather with a high of 15°C.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step10_BackgroundResponsesWithToolsAndPersistence",
            ProjectPath = "samples/02-agents/Agents/Agent_Step10_BackgroundResponsesWithToolsAndPersistence",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a generated novel or story.",
                "The output may include tool invocation messages like '[ResearchSpaceFacts]' or '[GenerateCharacterProfiles]'.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step11_Middleware",
            ProjectPath = "samples/02-agents/Agents/Agent_Step11_Middleware",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            // Example 4 prompts for approval; provide "Y" for each possible tool call
            Inputs = ["Y", "Y", "Y"],
            InputDelayMs = 3000,
            ExpectedOutputDescription =
            [
                "The output should contain multiple examples demonstrating different middleware patterns.",
                "It should include sections with '===' headers for different middleware examples.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step12_Plugins",
            ProjectPath = "samples/02-agents/Agents/Agent_Step12_Plugins",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain information about both the current time and the weather in Seattle.",
                "The weather information should reference the plugin result: cloudy with a high of 15°C.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step13_ChatReduction",
            ProjectPath = "samples/02-agents/Agents/Agent_Step13_ChatReduction",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = ["Chat history has", "messages."],
            ExpectedOutputDescription =
            [
                "The output should contain joke responses about a pirate, a robot, and a lemur.",
                "Between each response there should be a 'Chat history has N messages.' line showing the message count.",
                "There should be a fourth response after the user asks about the first joke. Due to chat reduction, the agent may not remember the pirate joke — any response is acceptable (including repeating another joke or saying it doesn't remember).",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step14_BackgroundResponses",
            ProjectPath = "samples/02-agents/Agents/Agent_Step14_BackgroundResponses",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a generated story or novel text about otters in space.",
                "The text may appear in two parts: first a polled-to-completion result, then a streamed continuation.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step16_Declarative",
            ProjectPath = "samples/02-agents/Agents/Agent_Step16_Declarative",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a response in JSON format with 'language' and 'answer' fields, since the declarative agent is configured to respond in JSON.",
                "The content should be a joke about a pirate in English.",
                "There should be both a non-streaming and streaming response.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step17_AdditionalAIContext",
            ProjectPath = "samples/02-agents/Agents/Agent_Step17_AdditionalAIContext",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show a personal assistant managing a todo list across multiple turns.",
                "The assistant should acknowledge adding items like picking up milk, taking Sally to soccer practice, and making a dentist appointment for Jimmy.",
                "There should be a JSON block showing the serialized session state.",
                "The final response should reference the calendar appointments (doctor at 15:00, team meeting at 17:00, birthday party at 20:00).",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step18_CompactionPipeline",
            ProjectPath = "samples/02-agents/Agents/Agent_Step18_CompactionPipeline",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = ["[User]", "[Agent]"],
            ExpectedOutputDescription =
            [
                "The output should show a turn-by-turn conversation between [User] and [Agent] about shopping for electronics (laptops, keyboards, mice).",
                "The output may include '[Messages: #N]' lines showing chat history compaction.",
                "The agent should provide information about product prices from tool results.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step19_InFunctionLoopCheckpointing",
            ProjectPath = "samples/02-agents/Agents/Agent_Step19_InFunctionLoopCheckpointing",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_RESPONSES_STORE"],
            MustContain = ["=== Non-Streaming Mode ===", "=== Streaming Mode ==="],
            ExpectedOutputDescription =
            [
                "The output should show non-streaming and streaming modes demonstrating in-function-loop checkpointing with multi-turn conversations.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ── AgentSkills ─────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "Agent_Step01_FileBasedSkills",
            ProjectPath = "samples/02-agents/AgentSkills/Agent_Step01_FileBasedSkills",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain =
            [
                "Converting units with file-based skills",
                "Agent:",
            ],
            ExpectedOutputDescription =
            [
                "The output should show the agent converting 26.2 miles to kilometers and 75 kilograms to pounds.",
                "The response should contain approximate numeric values for both conversions.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ── AgentWithMemory ─────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "AgentWithMemory_Step01_ChatHistoryMemory",
            ProjectPath = "samples/02-agents/AgentWithMemory/AgentWithMemory_Step01_ChatHistoryMemory",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain two joke responses.",
                "The first joke should be about a pirate (as explicitly requested).",
                "The second joke should also be pirate-themed or similar to what the user likes, since the memory system should recall the user's preference for pirate jokes from the first session.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "AgentWithMemory_Step04_MemoryUsingFoundry",
            ProjectPath = "samples/02-agents/AgentWithMemory/AgentWithMemory_Step04_MemoryUsingFoundry",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MEMORY_STORE_ID", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "AZURE_AI_EMBEDDING_DEPLOYMENT_NAME"],
            MustContain =
            [
                ">> Setting up Foundry Memory Store",
                ">> Serialize and deserialize the session to demonstrate persisted state",
                ">> Start a new session that shares the same Foundry Memory scope",
            ],
            ExpectedOutputDescription =
            [
                "The output should show a Foundry Memory Store being set up and processing updates.",
                "After serialization/deserialization, the agent should recall previously learned information.",
                "In the new session section, the agent should know facts from the earlier session due to shared Foundry Memory.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "AgentWithMemory_Step05_BoundedChatHistory",
            ProjectPath = "samples/02-agents/AgentWithMemory/AgentWithMemory_Step05_BoundedChatHistory",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"],
            MustContain =
            [
                "--- Filling the session window",
                "--- Next exchange will trigger overflow to vector store ---",
                "--- Asking about overflowed information",
            ],
            ExpectedOutputDescription =
            [
                "The output should demonstrate bounded chat history with overflow to a vector store.",
                "After the window fills up and overflows, the agent should still be able to recall older information (like a favorite color) from the vector store.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ── AgentWithRAG ────────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "AgentWithRAG_Step01_BasicTextRAG",
            ProjectPath = "samples/02-agents/AgentWithRAG/AgentWithRAG_Step01_BasicTextRAG",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"],
            MustContain = [">> Asking about returns", ">> Asking about shipping", ">> Asking about product care"],
            ExpectedOutputDescription =
            [
                "The returns section should mention a 30-day return policy, unused condition, and original packaging.",
                "The shipping section should mention 3-5 business days for standard shipping.",
                "The product care section should mention tent fabric maintenance tips like using lukewarm water, non-detergent soap, and air drying.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "AgentWithRAG_Step03_CustomRAGDataSource",
            ProjectPath = "samples/02-agents/AgentWithRAG/AgentWithRAG_Step03_CustomRAGDataSource",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            MustContain = [">> Asking about returns", ">> Asking about shipping", ">> Asking about product care"],
            ExpectedOutputDescription =
            [
                "The returns section should mention a 30-day return policy.",
                "The shipping section should mention 3-5 business days for standard shipping.",
                "The product care section should mention tent fabric maintenance tips.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "AgentWithRAG_Step04_FoundryServiceRAG",
            ProjectPath = "samples/02-agents/AgentWithRAG/AgentWithRAG_Step04_FoundryServiceRAG",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            MustContain = [">> Asking about returns", ">> Asking about shipping", ">> Asking about product care"],
            ExpectedOutputDescription =
            [
                "The returns section should mention a 30-day return policy.",
                "The shipping section should mention standard shipping timeframes.",
                "The product care section should mention tent fabric maintenance tips.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ── AgentsWithFoundry ────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "FoundryAgent_Step00_FoundryAgentLifecycle",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step00_FoundryAgentLifecycle",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step01_Basics",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step01_Basics",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke response from the agent.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step02.1_MultiturnConversation",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step02.1_MultiturnConversation",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain multiple joke responses showing a multi-turn conversation.",
                "There should be both non-streaming and streaming responses, with the second turn in each building on the first (e.g., adding emojis or pirate voice).",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step02.2_MultiturnWithServerConversations",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step02.2_MultiturnWithServerConversations",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should demonstrate server-side conversation sessions with non-streaming and streaming turns.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step03_UsingFunctionTools",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step03_UsingFunctionTools",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain weather information about Amsterdam from a function tool.",
                "The response should mention cloudy weather with a high of 15°C (from the canned tool response).",
                "There should be both a non-streaming and streaming response.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step04_UsingFunctionToolsWithApprovals",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step04_UsingFunctionToolsWithApprovals",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["Y", "Y", "Y"],
            InputDelayMs = 3000,
            ExpectedOutputDescription =
            [
                "The output should contain a prompt asking the user to approve a tool call, followed by weather information about Amsterdam.",
                "The response should mention cloudy weather with a high of 15°C.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step05_StructuredOutput",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step05_StructuredOutput",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            MustContain = ["Assistant Output:", "Name:"],
            ExpectedOutputDescription =
            [
                "The output should contain structured person information with Name, Age, and Occupation fields.",
                "There should be both a direct structured output and a streamed-then-deserialized output.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step06_PersistedConversations",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step06_PersistedConversations",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a pirate joke, then after session persistence, a second response retelling the joke in pirate voice with emojis.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step08_DependencyInjection",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step08_DependencyInjection",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["Tell me a joke about a pirate", ""],
            InputDelayMs = 5000,
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate in response to the user's request.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step10_UsingImages",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step10_UsingImages",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should describe an image of a nature walkway or boardwalk scene.",
                "It should mention elements like a wooden path, greenery, and an outdoor setting.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step11_AsFunctionTool",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step11_AsFunctionTool",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should be a response about the weather in Amsterdam, written in French.",
                "The response should reference the tool result: cloudy weather with a high of 15°C.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step12_Middleware",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step12_Middleware",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["Y", "Y", "Y"],
            InputDelayMs = 3000,
            ExpectedOutputDescription =
            [
                "The output should contain multiple middleware examples with '===' section headers.",
                "The human-in-the-loop example should show tool approval prompts and agent responses.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step13_Plugins",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step13_Plugins",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain information about both the current time and the weather in Seattle.",
                "The weather information should reference the plugin result: cloudy with a high of 15°C.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step14_CodeInterpreter",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step14_CodeInterpreter",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show the code interpreter being used to solve sin(x) + x^2 = 42, including a 'Code Input:' section with Python code.",
                "It should show a 'Code Input:' section with Python code for the math problem.",
                "It may show a 'Code Tool Result:' section with computed answers, or annotations with file references.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step16_FileSearch",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step16_FileSearch",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            MustContain = ["--- Running File Search Agent ---"],
            ExpectedOutputDescription =
            [
                "The output should show a file being uploaded and indexed in a vector store, then an agent answering a question based on the file content.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step17_OpenAPITools",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step17_OpenAPITools",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a list of countries or information about countries that use the EUR currency.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        // ── Skipped samples ─────────────────────────────────────────────────

        new SampleDefinition
        {
            Name = "AgentOpenTelemetry",
            ProjectPath = "samples/02-agents/AgentOpenTelemetry",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "Requires Aspire Dashboard / Docker for OpenTelemetry collection.",
        },

        new SampleDefinition
        {
            Name = "Agent_With_A2A",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_A2A",
            RequiredEnvironmentVariables = ["A2A_AGENT_HOST"],
            SkipReason = "Requires an external A2A agent host.",
        },

        new SampleDefinition
        {
            Name = "Agent_With_Anthropic",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_Anthropic",
            RequiredEnvironmentVariables = ["ANTHROPIC_API_KEY"],
            OptionalEnvironmentVariables = ["ANTHROPIC_CHAT_MODEL_NAME", "ANTHROPIC_RESOURCE"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_GitHubCopilot",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_GitHubCopilot",
            RequiredEnvironmentVariables = [],
            // The sample prompts for shell command approval; provide "Y" for each possible permission request
            Inputs = ["Y", "Y", "Y"],
            InputDelayMs = 3000,
            ExpectedOutputDescription =
            [
                "The output should contain a user prompt and a response listing files in the current directory.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_GoogleGemini",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_GoogleGemini",
            RequiredEnvironmentVariables = ["GOOGLE_GENAI_API_KEY"],
            OptionalEnvironmentVariables = ["GOOGLE_GENAI_MODEL"],
            MustContain =
            [
                "Google GenAI client based agent response:",
                "Community client based agent response:",
            ],
            ExpectedOutputDescription =
            [
                "The output should contain two labeled sections, each with a joke about a pirate from a different Gemini client.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_ONNX",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_ONNX",
            RequiredEnvironmentVariables = ["ONNX_MODEL_PATH"],
            SkipReason = "Requires local ONNX model.",
        },

        new SampleDefinition
        {
            Name = "Agent_With_Ollama",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_Ollama",
            RequiredEnvironmentVariables = ["OLLAMA_ENDPOINT", "OLLAMA_MODEL_NAME"],
            SkipReason = "Requires local Ollama server.",
        },

        new SampleDefinition
        {
            Name = "Agent_With_OpenAIAssistants",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_OpenAIAssistants",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate from the OpenAI Assistants API.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_OpenAIChatCompletion",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_OpenAIChatCompletion",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_With_OpenAIResponses",
            ProjectPath = "samples/02-agents/AgentProviders/Agent_With_OpenAIResponses",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Step05_Observability",
            ProjectPath = "samples/02-agents/Agents/Agent_Step05_Observability",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME", "APPLICATIONINSIGHTS_CONNECTION_STRING"],
            SkipReason = "Requires Application Insights / OpenTelemetry infrastructure.",
        },

        new SampleDefinition
        {
            Name = "Agent_Step07_AsMcpTool",
            ProjectPath = "samples/02-agents/Agents/Agent_Step07_AsMcpTool",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            SkipReason = "Runs as an MCP stdio server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "Agent_Step15_DeepResearch",
            ProjectPath = "samples/02-agents/Agents/Agent_Step15_DeepResearch",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "AZURE_AI_BING_CONNECTION_ID"],
            OptionalEnvironmentVariables = ["AZURE_AI_REASONING_DEPLOYMENT_NAME"],
            SkipReason = "Requires Azure AI Foundry project with Bing search connection.",
        },

        new SampleDefinition
        {
            Name = "Agent_Anthropic_Step01_Running",
            ProjectPath = "samples/02-agents/AgentWithAnthropic/Agent_Anthropic_Step01_Running",
            RequiredEnvironmentVariables = ["ANTHROPIC_API_KEY"],
            OptionalEnvironmentVariables = ["ANTHROPIC_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "There should be two responses — one from a non-streaming call and one from a streaming call.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Anthropic_Step02_Reasoning",
            ProjectPath = "samples/02-agents/AgentWithAnthropic/Agent_Anthropic_Step02_Reasoning",
            RequiredEnvironmentVariables = ["ANTHROPIC_API_KEY"],
            OptionalEnvironmentVariables = ["ANTHROPIC_CHAT_MODEL_NAME"],
            MustContain =
            [
                "1. Non-streaming:",
                "#### Start Thinking ####",
                "#### End Thinking ####",
                "#### Final Answer ####",
                "Token usage:",
                "2. Streaming",
            ],
            ExpectedOutputDescription =
            [
                "The non-streaming section should show the agent's reasoning about a math problem, followed by a final answer.",
                "The streaming section should show reasoning and a response about the theory of relativity.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Anthropic_Step03_UsingFunctionTools",
            ProjectPath = "samples/02-agents/AgentWithAnthropic/Agent_Anthropic_Step03_UsingFunctionTools",
            RequiredEnvironmentVariables = ["ANTHROPIC_API_KEY"],
            OptionalEnvironmentVariables = ["ANTHROPIC_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain information about the weather in Amsterdam.",
                "There should be two responses — one from a non-streaming call and one from a streaming call.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_Anthropic_Step04_UsingSkills",
            ProjectPath = "samples/02-agents/AgentWithAnthropic/Agent_Anthropic_Step04_UsingSkills",
            RequiredEnvironmentVariables = ["ANTHROPIC_API_KEY"],
            OptionalEnvironmentVariables = ["ANTHROPIC_CHAT_MODEL_NAME"],
            MustContain =
            [
                "Creating a presentation about renewable energy...",
                "#### Agent Response ####",
            ],
            ExpectedOutputDescription =
            [
                "The output should show the agent creating a presentation about renewable energy.",
                "There should be an agent response section with content about renewable energy sources.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "AgentWithMemory_Step02_MemoryUsingMem0",
            ProjectPath = "samples/02-agents/AgentWithMemory/AgentWithMemory_Step02_MemoryUsingMem0",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME", "MEM0_ENDPOINT", "MEM0_API_KEY"],
            SkipReason = "Requires Mem0 service.",
        },

        new SampleDefinition
        {
            Name = "Agent_OpenAI_Step01_Running",
            ProjectPath = "samples/02-agents/AgentWithOpenAI/Agent_OpenAI_Step01_Running",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_OpenAI_Step02_Reasoning",
            ProjectPath = "samples/02-agents/AgentWithOpenAI/Agent_OpenAI_Step02_Reasoning",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            MustContain =
            [
                "1. Non-streaming:",
                "Token usage:",
                "2. Streaming",
            ],
            ExpectedOutputDescription =
            [
                "The non-streaming section should show the agent's reasoning about a math problem, followed by a final answer.",
                "The streaming section should show reasoning and a response about the theory of relativity.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_OpenAI_Step03_CreateFromChatClient",
            ProjectPath = "samples/02-agents/AgentWithOpenAI/Agent_OpenAI_Step03_CreateFromChatClient",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "There should be two responses — one from a non-streaming call and one from a streaming call.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_OpenAI_Step04_CreateFromOpenAIResponseClient",
            ProjectPath = "samples/02-agents/AgentWithOpenAI/Agent_OpenAI_Step04_CreateFromOpenAIResponseClient",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            ExpectedOutputDescription =
            [
                "The output should contain a joke about a pirate.",
                "There should be two responses — one from a non-streaming call and one from a streaming call.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "Agent_OpenAI_Step05_Conversation",
            ProjectPath = "samples/02-agents/AgentWithOpenAI/Agent_OpenAI_Step05_Conversation",
            RequiredEnvironmentVariables = ["OPENAI_API_KEY"],
            OptionalEnvironmentVariables = ["OPENAI_CHAT_MODEL_NAME"],
            MustContain =
            [
                "=== Multi-turn Conversation Demo ===",
                "Conversation created.",
                "Conversation ID:",
            ],
            ExpectedOutputDescription =
            [
                "The output should show a multi-turn conversation about France: capital, landmarks, and height of the most famous one.",
                "The output should show the conversation history retrieved from the server.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "AgentWithRAG_Step02_CustomVectorStoreRAG",
            ProjectPath = "samples/02-agents/AgentWithRAG/AgentWithRAG_Step02_CustomVectorStoreRAG",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"],
            SkipReason = "Requires external Qdrant vector store.",
        },

        new SampleDefinition
        {
            Name = "DeclarativeAgents_ChatClient",
            ProjectPath = "samples/02-agents/DeclarativeAgents/ChatClient",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "Requires command-line arguments (YAML file path) with no YAML files checked in.",
        },

        new SampleDefinition
        {
            Name = "DevUI_Step01_BasicUsage",
            ProjectPath = "samples/02-agents/DevUI/DevUI_Step01_BasicUsage",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "ASP.NET Core web server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step07_Observability",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step07_Observability",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME", "APPLICATIONINSIGHTS_CONNECTION_STRING"],
            SkipReason = "Requires Application Insights / OpenTelemetry infrastructure.",
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step09_UsingMcpClientAsTools",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step09_UsingMcpClientAsTools",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show an agent using the Microsoft Learn MCP tool to search or retrieve documentation.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step15_ComputerUse",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step15_ComputerUse",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription = ["The output should show a computer automation session processing simulated browser screenshots with iteration steps and a final response describing search results."],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step18_BingCustomSearch",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step18_BingCustomSearch",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "AZURE_AI_CUSTOM_SEARCH_CONNECTION_ID", "AZURE_AI_CUSTOM_SEARCH_INSTANCE_NAME"],
            SkipReason = "Requires Bing Custom Search connection.",
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step19_SharePoint",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step19_SharePoint",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "SHAREPOINT_PROJECT_CONNECTION_ID"],
            SkipReason = "Requires SharePoint connection.",
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step20_MicrosoftFabric",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step20_MicrosoftFabric",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "FABRIC_PROJECT_CONNECTION_ID"],
            SkipReason = "Requires Microsoft Fabric connection.",
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step21_WebSearch",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step21_WebSearch",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription =
            [
                "The output should show an agent using web search to answer a question, with response text and citation annotations.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step22_MemorySearch",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step22_MemorySearch",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "AZURE_AI_EMBEDDING_DEPLOYMENT_NAME"],
            OptionalEnvironmentVariables = ["AZURE_AI_MEMORY_STORE_ID"],
            MustContain = ["Agent created with Memory Search tool. Starting conversation..."],
            ExpectedOutputDescription =
            [
                "The output should show a memory store being created, memories stored from a prior conversation, and an agent querying those memories.",
                "The output should not contain error messages or stack traces.",
            ],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Step23_LocalMCP",
            ProjectPath = "samples/02-agents/AgentsWithFoundry/Agent_Step23_LocalMCP",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ExpectedOutputDescription = ["The output should show an agent using the Microsoft Learn MCP server to search for documentation and provide a response."],
        },

        new SampleDefinition
        {
            Name = "FoundryAgent_Hosted_MCP",
            ProjectPath = "samples/02-agents/ModelContextProtocol/FoundryAgent_Hosted_MCP",
            RequiredEnvironmentVariables = ["AZURE_AI_PROJECT_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            Inputs = ["Y", "Y", "Y", "Y", "Y"],
            InputDelayMs = 5000,
            ExpectedOutputDescription = ["The output should contain a summary or information about Azure AI documentation from Microsoft Learn."],
        },

        new SampleDefinition
        {
            Name = "ResponseAgent_Hosted_MCP",
            ProjectPath = "samples/02-agents/ModelContextProtocol/ResponseAgent_Hosted_MCP",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            Inputs = ["Y", "Y", "Y", "Y", "Y"],
            InputDelayMs = 5000,
            ExpectedOutputDescription = ["The output should contain a summary or information about Azure AI documentation from Microsoft Learn."],
        },

        new SampleDefinition
        {
            Name = "Agent_MCP_Server",
            ProjectPath = "samples/02-agents/ModelContextProtocol/Agent_MCP_Server",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "Runs as an MCP stdio server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "Agent_MCP_Server_Auth",
            ProjectPath = "samples/02-agents/ModelContextProtocol/Agent_MCP_Server_Auth",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "Runs as an MCP stdio server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step01_GettingStarted_Client",
            ProjectPath = "samples/02-agents/AGUI/Step01_GettingStarted/Client",
            RequiredEnvironmentVariables = [],
            SkipReason = "Multi-process client/server architecture; requires AGUI server running.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step01_GettingStarted_Server",
            ProjectPath = "samples/02-agents/AGUI/Step01_GettingStarted/Server",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "ASP.NET Core web server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step02_BackendTools_Client",
            ProjectPath = "samples/02-agents/AGUI/Step02_BackendTools/Client",
            RequiredEnvironmentVariables = [],
            SkipReason = "Multi-process client/server architecture; requires AGUI server running.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step02_BackendTools_Server",
            ProjectPath = "samples/02-agents/AGUI/Step02_BackendTools/Server",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "ASP.NET Core web server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step03_FrontendTools_Client",
            ProjectPath = "samples/02-agents/AGUI/Step03_FrontendTools/Client",
            RequiredEnvironmentVariables = [],
            SkipReason = "Multi-process client/server architecture; requires AGUI server running.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step03_FrontendTools_Server",
            ProjectPath = "samples/02-agents/AGUI/Step03_FrontendTools/Server",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "ASP.NET Core web server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step04_HumanInLoop_Client",
            ProjectPath = "samples/02-agents/AGUI/Step04_HumanInLoop/Client",
            RequiredEnvironmentVariables = [],
            SkipReason = "Multi-process client/server architecture; requires AGUI server running.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step04_HumanInLoop_Server",
            ProjectPath = "samples/02-agents/AGUI/Step04_HumanInLoop/Server",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "ASP.NET Core web server that does not exit on its own.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step05_StateManagement_Client",
            ProjectPath = "samples/02-agents/AGUI/Step05_StateManagement/Client",
            RequiredEnvironmentVariables = [],
            SkipReason = "Multi-process client/server architecture; requires AGUI server running.",
        },

        new SampleDefinition
        {
            Name = "AGUI_Step05_StateManagement_Server",
            ProjectPath = "samples/02-agents/AGUI/Step05_StateManagement/Server",
            RequiredEnvironmentVariables = ["AZURE_OPENAI_ENDPOINT"],
            OptionalEnvironmentVariables = ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            SkipReason = "ASP.NET Core web server that does not exit on its own.",
        },
    ];
}

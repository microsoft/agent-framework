// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Declarative.UnitTests;
internal static class PromptAgents
{
    internal const string AgentWithEverything =
    """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIResponsesModel
          id: gpt-4o
          options:
            temperature: 0.7
            maxOutputTokens: 1024
            topP: 0.9
            topK: 50
            frequencyPenalty: 0.0
            presencePenalty: 0.0
            seed: 42
            responseFormat: text
            stopSequences:
              - "###"
              - "END"
              - "STOP"
            allowMultipleToolCalls: true
        tools:
          - kind: codeInterpreter
          - kind: function
            name: GetWeather
            description: Get the weather for a given location.
            parameters:
              - name: location
                type: string
                description: The city and state, e.g. San Francisco, CA
                required: true
              - name: unit
                type: string
                description: The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.
                required: false
                enum:
                  - celsius
                  - fahrenheit
          - kind: mcp
            name: PersonInfoTool
            description: Get information about a person.
            url: https://my-mcp-endpoint.com/api
          - kind: webSearch
            name: WebSearchTool
            description: Search the web for information.
          - kind: fileSearch
            name: FileSearchTool
            description: Search files for information.
            vectorStoreIds:
              - 1
              - 2
              - 3
        """;

    internal const string AgentWithOutputSchema =
        """
        kind: Prompt
        name: Translation Assistant
        description: A helpful assistant that translates text to a specified language.
        model:
            kind: OpenAIResponsesModel
            id: gpt-4o
            options:
                temperature: 0.9
                topP: 0.95
        instructions: You are a helpful assistant. You answer questions in {language}. You return your answers in a JSON format.
        additionalInstructions: You must always respond in the specified language.
        tools:
          - kind: codeInterpreter
        template:
            format: PowerFx # Mustache is the other option
            parser: None # Prompty and XML are the other options
        inputSchema:
            properties:
                language: string
        outputSchema:
            properties:
                language:
                    type: string
                    required: true
                    description: The language of the answer.
                answer:
                    type: string
                    required: true
                    description: The answer text.
        """;

    internal const string AgentWithKeyConnection =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIResponsesModel
          id: gpt-4o
          connection:
            kind: Key
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
            key: my-api-key
        """;

    internal const string AgentWithEnvironmentVariables =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIResponsesModel
          id: =Env.OpenAIModelId
          connection:
            kind: Key
            endpoint: =Env.OpenAIEndpoint
            key: =Env.OpenAIApiKey
        """;

    internal const string OpenAIChatAgent =
        """
        kind: Prompt
        name: Assistant
        description: Helpful assistant
        instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
        model:
            kind: OpenAIResponsesModel
            id: =Env.OPENAI_MODEL
            options:
                temperature: 0.9
                topP: 0.95
            connection:
                kind: Key
                key: =Env.OPENAI_APIKEY
        outputSchema:
            properties:
                language:
                    type: string
                    required: true
                    description: The language of the answer.
                answer:
                    type: string
                    required: true
                    description: The answer text.        
        """;

    internal const string AgentWithOpenAIChatModel =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: ChatModel
          id: gpt-4o
          options:
            temperature: 0.7
            maxOutputTokens: 1024
            topP: 0.9
            topK: 50
            frequencyPenalty: 0.7
            presencePenalty: 0.7
            seed: 42
            responseFormat: text
            stopSequences:
              - "###"
              - "END"
              - "STOP"
            allowMultipleToolCalls: true
            chatToolMode: auto
        """;

    internal const string AgentWithOpenAIResponsesModelSnakeCase =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: OpenAIResponsesModel
          id: gpt-4o
          options:
            temperature: 0.7
            max_output_tokens: 1024
            top_p: 0.9
            top_k: 50
            frequency_penalty: 0.7
            presence_penalty: 0.7
            seed: 42
            response_format: text
            stop_sequences:
              - "###"
              - "END"
              - "STOP"
            allow_multiple_tool_calls: true
            chat_tool_mode: auto
        """;

    internal static readonly string[] s_stopSequences = ["###", "END", "STOP"];

    internal static GptComponentMetadata CreateTestPromptAgent(string? publisher = "OpenAI", string? apiType = "Chat")
    {
        string agentYaml =
            $"""
            kind: Prompt
            name: Test Agent
            description: Test Description
            instructions: You are a helpful assistant.
            additionalInstructions: Provide detailed and accurate responses.
            model:
              kind: OpenAIResponsesModel
              id: gpt-4o
              publisher: {publisher}
              apiType: {apiType}
              options:
                modelId: gpt-4o
                temperature: 0.7
                maxOutputTokens: 1024
                topP: 0.9
                topK: 50
                frequencyPenalty: 0.7
                presencePenalty: 0.7
                seed: 42
                responseFormat: text
                stopSequences:
                  - "###"
                  - "END"
                  - "STOP"
                allowMultipleToolCalls: true
                chatToolMode: auto
                customProperty: customValue
              connection:
                kind: Key
                endpoint: https://my-azure-openai-endpoint.openai.azure.com/
                key: my-api-key
            tools:
              - kind: codeInterpreter
              - kind: function
                name: GetWeather
                description: Get the weather for a given location.
                parameters:
                  - name: location
                    type: string
                    description: The city and state, e.g. San Francisco, CA
                    required: true
                  - name: unit
                    type: string
                    description: The unit of temperature. Possible values are 'celsius' and 'fahrenheit'.
                    required: false
                    enum:
                      - celsius
                      - fahrenheit
              - kind: mcp
                name: PersonInfoTool
                description: Get information about a person.
                url: https://my-mcp-endpoint.com/api
              - kind: webSearch
                name: WebSearchTool
                description: Search the web for information.
              - kind: fileSearch
                name: FileSearchTool
                description: Search files for information.
                vectorStoreIds:
                  - 1
                  - 2
                  - 3
            outputSchema:
                properties:
                    language:
                        type: string
                        required: true
                        description: The language of the answer.
                    answer:
                        type: string
                        required: true
                        description: The answer text.
            """;

        return AgentBotElementYaml.FromYaml(agentYaml);
    }
}

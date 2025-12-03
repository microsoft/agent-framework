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
            inputs:
              - kind: HostedFileContent
                FileId: fileId123
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
            serverName: PersonInfoTool
            serverDescription: Get information about a person.
            connection:
                kind: AnonymousConnection
                endpoint: https://my-mcp-endpoint.com/api
            allowedTools:
              - "GetPersonInfo"
              - "UpdatePersonInfo"
              - "DeletePersonInfo"
            approvalMode:
              kind: HostedMcpServerToolRequireSpecificApprovalMode
              AlwaysRequireApprovalToolNames:
                - "UpdatePersonInfo"
                - "DeletePersonInfo"
              NeverRequireApprovalToolNames:
                - "GetPersonInfo"
          - kind: webSearch
            name: WebSearchTool
            description: Search the web for information.
          - kind: fileSearch
            name: FileSearchTool
            description: Search files for information.
            ranker: default
            scoreThreshold: 0.5
            maxResults: 5
            maxContentLength: 2000
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

    internal const string AgentWithApiKeyConnection =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          id: gpt-4o
          connection:
            kind: ApiKey
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
            key: my-api-key
        """;

    internal const string AgentWithRemoteConnection =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          id: gpt-4o
          connection:
            kind: Remote
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
        """;

    internal const string AgentWithVariableReferences =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          id: gpt-4o
          options:
            temperature: =Env.Temperature
            topP: =Env.TopP
          connection:
            kind: apiKey
            endpoint: =Env.OpenAIEndpoint
            key: =Env.OpenAIApiKey
        """;

    internal const string OpenAIChatAgent =
        """
        kind: Prompt
        name: Assistant
        description: Helpful assistant
        instructions: You are a helpful assistant. You answer questions in the language specified by the user. You return your answers in a JSON format.
        model:
            id: =Env.OPENAI_MODEL
            options:
                temperature: 0.9
                topP: 0.95
            connection:
                kind: apiKey
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

    internal const string AgentWithCurrentModels =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
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

    internal const string AgentWithCurrentModelsSnakeCase =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
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

    internal const string Workflow =
        """
        kind: Workflow
        trigger:

          kind: OnConversationStart
          id: workflow_demo
          actions:

            - kind: InvokeAzureAgent
              id: question_student
              conversationId: =System.ConversationId
              agent:
                name: StudentAgent

            - kind: InvokeAzureAgent
              id: question_teacher
              conversationId: =System.ConversationId
              agent:
                name: TeacherAgent
              output:
                messages: Local.TeacherResponse

            - kind: SetVariable
              id: set_count_increment
              variable: Local.TurnCount
              value: =Local.TurnCount + 1

            - kind: ConditionGroup
              id: check_completion
              conditions:

                - condition: =!IsBlank(Find("CONGRATULATIONS", Upper(MessageText(Local.TeacherResponse))))
                  id: check_turn_done
                  actions:

                    - kind: SendActivity
                      id: sendActivity_done
                      activity: GOLD STAR!

                - condition: =Local.TurnCount < 4
                  id: check_turn_count
                  actions:

                    - kind: GotoAction
                      id: goto_student_agent
                      actionId: question_student

              elseActions:

                - kind: SendActivity
                  id: sendActivity_tired
                  activity: Let's try again later...
        
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
                kind: apiKey
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
                serverName: PersonInfoTool
                serverDescription: Get information about a person.
                allowedTools:
                  - "GetPersonInfo"
                  - "UpdatePersonInfo"
                  - "DeletePersonInfo"
                approvalMode:
                  kind: HostedMcpServerToolRequireSpecificApprovalMode
                  AlwaysRequireApprovalToolNames:
                    - "UpdatePersonInfo"
                    - "DeletePersonInfo"
                  NeverRequireApprovalToolNames:
                    - "GetPersonInfo"
                connection:
                    kind: AnonymousConnection
                    endpoint: https://my-mcp-endpoint.com/api
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

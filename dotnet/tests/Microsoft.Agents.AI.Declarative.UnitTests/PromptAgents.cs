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
          kind: ExternalModel
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
            description: Get information about a person.
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
            Inputs:
              - kind: VectorStoreContent
                vectorStoreId: 1
              - kind: VectorStoreContent
                vectorStoreId: 2
              - kind: VectorStoreContent
                vectorStoreId: 3
        """;

    internal const string AgentWithOutputSchema =
        """
        kind: Prompt
        name: Translation Assistant
        description: A helpful assistant that translates text to a specified language.
        model:
            kind: ExternalModel
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
          kind: ExternalModel
          id: gpt-4o
          connection:
            kind: ApiKey
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
            key: my-api-key
        """;

    internal const string AgentWithFoundryConnection =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: ExternalModel
          id: gpt-4o
          connection:
            kind: Foundry
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
        """;

    internal const string AgentWithEnvironmentVariables =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: ExternalModel
          id: =Env.OpenAIModelId
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
        instructions: You are a helpful assistant. You answer questions is the language specified by the user. You return your answers in a JSON format.
        model:
            kind: ExternalModel
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

    internal const string AgentWithExternalModel =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: ExternalModel
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

    internal const string AgentWithExternalModelSnakeCase =
        """
        kind: Prompt
        name: AgentName
        description: Agent description
        instructions: You are a helpful assistant.
        model:
          kind: ExternalModel
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

    internal const string AgentForSalesAnalyst =
        """
        name: sales-analyst-agent
        displayName: Sales Analyst Agent

        description: |-
          This agent helps users analyze sales data by leveraging the Code Interpreter tool
          for data analysis and a File Search tool to access uploaded sales documents.
          The agent provides insights on sales performance, customer trends, and product analysis.

        metadata:
          tags:
            - example
            - analyst
          authors:
            - sethjuarez
            - jietong

        model:
          kind: ExternalModel
          id: gpt-4o
          connection:
            kind: ApiKey
            endpoint: https://my-azure-openai-endpoint.openai.azure.com/
            key: my-api-key


        tools:
          - kind: CustomTool
            connection:
              kind: AnonymousConnection
            options:
              customProperty1: true
              customProperty2: "value2"

          - kind: CodeInterpreter
            description: An API to extract intent from a given message.
            Inputs:
              - kind: HostedFileContent
                FileId: fileId123

          - kind: Function
            name: SalesDataAnalyzer
            description: Analyzes sales data to provide insights on sales performance, customer trends, and product analysis.
            InputSchema:
              properties:
                query:
                  type: string
                  required: true
                  description: The analysis query to be performed on the sales data.
            OutputSchema:
              properties:
                result:
                  type: string
                  description: The result of the sales data analysis.

          - kind: WebSearch

          - kind: BingSearch
            connection:
              name: bing_search_connection
            options:
              market: =Env.market
              setLanguage: en-us
              count: 10
              freshness: Month

          - kind: FileSearch
            description: An API to search files that have been uploaded to the agent.
            connection:
              name: file_search_connection
              authenticationMode: system
            ranker: default
            scoreThreshold: 0.5
            maxResults: 5
            maxContentLength: 2000
            Inputs:
              - kind: VectorStoreContent
                vectorStoreId: asdfghjklqwertyuiopzxcvbnm123456

          - kind: MCP
            serverName: github
            serverDescription: GitHub MCP Server
            allowedTools:
              - "SalesDataAnalyzer"
              - "CustomerInsightsGenerator"
            approvalMode:
              kind: HostedMcpServerToolRequireSpecificApprovalMode
              AlwaysRequireApprovalToolNames:
                - "SalesDataAnalyzer"
                - "CustomerInsightsGenerator"
              NeverRequireApprovalToolNames:
                - "FileSearch"

          - kind: OpenAPI
            connection:
              kind: ApiKey
              Key: =Env.ApiKey
            specification: |-
              openapi: 3.0.0
              info:
                title: Customer Insights API
                version: 1.0.0
              paths:
                /customer-insights:
                  post:
                    summary: Generate customer insights based on sales data.
                    requestBody:
                      required: true
                      content:
                        application/json:
                          schema:
                            type: object
                            properties:
                              salesData:
                                type: string
                                description: The sales data to analyze.
                    responses:
                      '200':
                        description: Successful response
                        content:
                          application/json:
                            schema:
                              type: object
                              properties:
                                insights:
                                  type: string
                                  description: {Env.test}

        instructions: |-
          You are an expert sales analyst.
          Use the uploaded sales data to answer questions about orders, customers, regions, and product performance.
          Always explain your reasoning and cite relevant files or calculations.

          This is an example of a Power Fx expression that should not be wrapped in an ExpressionSegment because the
          format is Mustache: {Env.test}

        template:
          format: Mustache
          parser: NoTemplateParser
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
              kind: ExternalModel
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
                description: Get information about a person.
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

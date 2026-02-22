// Copyright (c) Microsoft. All rights reserved.

using AgentWebChat.AppHost;

var builder = DistributedApplication.CreateBuilder(args);

/* Setup for actual application using existing Azure OpenAI resources
var azOpenAiResource = builder.AddParameterFromConfiguration("AzureOpenAIName", "AzureOpenAI:Name");
var azOpenAiResourceGroup = builder.AddParameterFromConfiguration("AzureOpenAIResourceGroup", "AzureOpenAI:ResourceGroup");
var chatModel = builder.AddAIModel("chat-model").AsAzureOpenAI("gpt-4o", o => o.AsExisting(azOpenAiResource, azOpenAiResourceGroup));
*/

// Setup for local development/testing with multiple providers for Sample application
#pragma warning disable ASPIREINTERACTION001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
var endpoint = builder.AddParameter("Endpoint")
    .WithCustomInput(parameter => new InteractionInput()
    {
        Name = parameter.Name,
        InputType = InputType.Text,
        Value = "NaN",
        Label = parameter.Name,
        Placeholder = "The endpoint for the provider if applicable",
        Description = "Endpoint for the provider. **Note:** If not applicable, enter 'NaN'",
        EnableDescriptionMarkdown = true
    });
var accessKey = builder.AddParameter("AccessKey")
    .WithCustomInput(parameter => new InteractionInput()
    {
        Name = parameter.Name,
        InputType = InputType.SecretText,
        Label = parameter.Name,
        Value = "NaN",
        Placeholder = "The accessKey or apiKey for the provider if applicable",
        Description = "AccessKey or API key for the provider. **Note:** If not applicable, enter 'NaN'",
        EnableDescriptionMarkdown = true
    });
var model = builder.AddParameter("Model")
    .WithCustomInput(parameter => new InteractionInput()
    {
        Name = parameter.Name,
        InputType = InputType.Text,
        Label = parameter.Name,
        Placeholder = "The AI model"
    });
var provider = builder.AddParameter("Provider")
    .WithCustomInput(parameter => new InteractionInput()
    {
        Name = parameter.Name,
        InputType = InputType.Choice,
        Options = new[]
        {
            KeyValuePair.Create("AzureOpenAI", "AzureOpenAI"),
            KeyValuePair.Create("OpenAI", "OpenAI Compatible"),
            KeyValuePair.Create("Ollama", "Ollama"),
        },
        Label = parameter.Name,
        Placeholder = "The provider for the AI model",
        Description = """
        **OpenAI Compatible**: Required `Model`, `Endpoint` and `AccessKey`

        **AzureOpenAI**: Required `Model` and DefaultAzureCredentials will be used for authentication.

        **Ollama**: Required `Model` and `Endpoint`
        """,
        EnableDescriptionMarkdown = true
    });
#pragma warning restore ASPIREINTERACTION001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

var chatModel = builder.AddAIModel("chat-model", endpoint, accessKey, model, provider);

var agentHost = builder.AddProject<Projects.AgentWebChat_AgentHost>("agenthost")
    .WithHttpEndpoint(name: "devui")
    .WithUrlForEndpoint("devui", (url) => new() { Url = "/devui", DisplayText = "Dev UI" })
    .WithReference(chatModel);

builder.AddProject<Projects.AgentWebChat_Web>("webfrontend")
    .WithExternalHttpEndpoints()
    .WithReference(agentHost)
    .WaitFor(agentHost);

builder.Build().Run();

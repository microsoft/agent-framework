# DevUI Step 01 - Basic Usage

This sample demonstrates how to add the DevUI to an ASP.NET Core application with AI agents.

## What is DevUI?

The DevUI provides an interactive web interface for testing and debugging AI agents during development.

## Configuration

Set the following environment variables:

- `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint URL (required)
- `AZURE_OPENAI_DEPLOYMENT_NAME` - Your deployment name (defaults to "gpt-4o-mini")

## Running the Sample

1. Set your Azure OpenAI credentials as environment variables
2. Run the application:
   ```bash
   dotnet run
   ```
3. Open your browser to https://localhost:64704/devui
4. Select an agent or workflow from the dropdown and start chatting!

## Sample Agents and Workflows

This sample includes:

**Agents:**
- **assistant** - A helpful assistant
- **poet** - A creative poet
- **coder** - An expert programmer

**Workflows:**
- **review-workflow** - A sequential workflow that generates a response and then reviews it

## Adding DevUI to Your Own Project

To add DevUI to your ASP.NET Core application:

1. Add the DevUI package and hosting packages:
   ```bash
   dotnet add package Microsoft.Agents.AI.DevUI
   dotnet add package Microsoft.Agents.AI.Hosting
   dotnet add package Microsoft.Agents.AI.Hosting.OpenAI
   ```

2. Register your agents and workflows:
   ```csharp
   var builder = WebApplication.CreateBuilder(args);
   
   // Set up your chat client
   builder.Services.AddChatClient(chatClient);
   
   // Register agents
   builder.AddAIAgent("assistant", "You are a helpful assistant.");
   
   // Register workflows
   builder.AddSequentialWorkflow("my-workflow", [agent1, agent2])
       .AddAsAIAgent();
   ```

3. Add DevUI services and map the endpoint:
   ```csharp
   builder.AddDevUI();
   var app = builder.Build();
   
   if (app.Environment.IsDevelopment())
   {
       app.MapDevUI();
   }
   
   app.MapEntities();
   app.MapOpenAIResponses();
   app.MapConversations();
   
   app.Run();
   ```

4. Navigate to `/devui` in your browser

using Azure.AI.Agents.Persistent;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Agents.AzureAI;
using System.Reflection;
using System.Text;

// Define FOUNDRY_PROJECT_ENDPOINT as a user-secret or environment variable that
// points to your Foundry project endpoint.

IConfigurationRoot config =
        new ConfigurationBuilder()
            .AddUserSecrets(Assembly.GetExecutingAssembly())
            .AddEnvironmentVariables()
            .Build();

string projectEndpoint = config["FOUNDRY_PROJECT_ENDPOINT"] ?? throw new InvalidOperationException("Undefined configuration: FOUNDRY_PROJECT_ENDPOINT");
Console.WriteLine($"{Environment.NewLine}Foundry: {projectEndpoint}");

StringBuilder scriptBuilder = new();
StringBuilder secretBuilder = new();
string[] files = args.Length > 0 ? args : Directory.GetFiles(@"..\", "*.yaml");
foreach (string file in files)
{
    string agentText = await File.ReadAllTextAsync(file);

    PersistentAgentsClient clientAgents = new(projectEndpoint, new AzureCliCredential());

    AIProjectClient clientProject = new(new Uri(projectEndpoint), new AzureCliCredential());

    IKernelBuilder kernelBuilder = Kernel.CreateBuilder();
    kernelBuilder.Services.AddSingleton(clientAgents);
    kernelBuilder.Services.AddSingleton(clientProject);
    Kernel kernel = kernelBuilder.Build();

    AzureAIAgentFactory factory = new();
    Agent? agent = await factory.CreateAgentFromYamlAsync(agentText, new AgentCreationOptions() { Kernel = kernel }, config);
    if (agent is null)
    {
        Console.WriteLine("Unexpected failure creating agent...");
        continue;
    }    

    Console.WriteLine();
    Console.WriteLine(Path.GetFileName(file));
    Console.WriteLine($"  Id:   {agent?.Id ?? "???"}");
    Console.WriteLine($"  Name: {agent?.Name ?? agent?.Id}");
    Console.WriteLine($"  Note: {agent?.Description}");

    scriptBuilder.AppendLine($"$env:FOUNDRY_AGENT_{agent?.Name?.ToUpperInvariant()} = '{agent?.Id}'");
    secretBuilder.AppendLine($"dotnet user-secrets set FOUNDRY_AGENT_{agent?.Name?.ToUpperInvariant()} {agent?.Id}");
}

Console.WriteLine();
Console.WriteLine();
Console.WriteLine("To set these environment variables in your shell, run:");
Console.WriteLine();
Console.WriteLine(scriptBuilder);
Console.WriteLine();
Console.WriteLine();
Console.WriteLine("To define user secrets, run:");
Console.WriteLine();
Console.WriteLine(secretBuilder);
Console.WriteLine();

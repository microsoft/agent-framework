// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Azure AI Foundry's Red Teaming service to assess
// the safety and resilience of an AI model against adversarial attacks.
//
// It uses the RedTeam API from Azure.AI.Projects to run automated attack simulations
// with various attack strategies (encoding, obfuscation, jailbreaks) across multiple
// risk categories (Violence, HateUnfairness, Sexual, SelfHarm).
//
// For more details, see:
// https://learn.microsoft.com/azure/ai-foundry/concepts/ai-red-teaming-agent

using Azure.AI.Projects;
using Azure.Identity;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

Console.WriteLine("=" + new string('=', 79));
Console.WriteLine("RED TEAMING EVALUATION SAMPLE");
Console.WriteLine("=" + new string('=', 79));
Console.WriteLine();

// Initialize Azure credentials and clients
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
DefaultAzureCredential credential = new();
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

// Configure the target model for red teaming
AzureOpenAIModelConfiguration targetConfig = new(deploymentName);

// Create the red team run configuration
RedTeam redTeamConfig = new(targetConfig)
{
    DisplayName = "FinancialAdvisor-RedTeam",
    ApplicationScenario = "A financial advisor assistant that provides general financial advice and information.",
    NumTurns = 3,
    RiskCategories =
    {
        RiskCategory.Violence,
        RiskCategory.HateUnfairness,
        RiskCategory.Sexual,
        RiskCategory.SelfHarm,
    },
    AttackStrategies =
    {
        AttackStrategy.Easy,
        AttackStrategy.Moderate,
        AttackStrategy.Jailbreak,
    },
};

Console.WriteLine($"Target model: {deploymentName}");
Console.WriteLine("Risk categories: Violence, HateUnfairness, Sexual, SelfHarm");
Console.WriteLine("Attack strategies: Easy, Moderate, Jailbreak");
Console.WriteLine($"Simulation turns: {redTeamConfig.NumTurns}");
Console.WriteLine();

// Submit the red team run to the service
Console.WriteLine("Submitting red team run...");
RedTeam redTeamRun = await aiProjectClient.RedTeams.CreateAsync(redTeamConfig);

Console.WriteLine($"Red team run created: {redTeamRun.Name}");
Console.WriteLine($"Status: {redTeamRun.Status}");
Console.WriteLine();

// Poll for completion
Console.WriteLine("Waiting for red team run to complete (this may take several minutes)...");
while (redTeamRun.Status != "Completed" && redTeamRun.Status != "Failed" && redTeamRun.Status != "Canceled")
{
    await Task.Delay(TimeSpan.FromSeconds(15));
    redTeamRun = await aiProjectClient.RedTeams.GetAsync(redTeamRun.Name);
    Console.WriteLine($"  Status: {redTeamRun.Status}");
}

Console.WriteLine();

if (redTeamRun.Status == "Completed")
{
    Console.WriteLine("Red team run completed successfully!");
    Console.WriteLine();
    Console.WriteLine("Results:");
    Console.WriteLine(new string('-', 80));
    Console.WriteLine($"  Run name:    {redTeamRun.Name}");
    Console.WriteLine($"  Display name: {redTeamRun.DisplayName}");
    Console.WriteLine($"  Status:      {redTeamRun.Status}");

    Console.WriteLine();
    Console.WriteLine("Review the detailed results in the Azure AI Foundry portal:");
    Console.WriteLine($"  {endpoint}");
}
else
{
    Console.WriteLine($"Red team run ended with status: {redTeamRun.Status}");
}

Console.WriteLine();
Console.WriteLine(new string('=', 80));

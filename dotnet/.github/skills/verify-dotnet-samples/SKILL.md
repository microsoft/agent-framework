---
name: verify-dotnet-samples
description: How to build, run and verify the .NET sample projects in the Agent Framework repository. Use this when a user wants to verify that the samples still function as expected.
---

# Verifying .NET Sample Projects

## Sample Pre-requisites

We should only support verifying samples that:
1. Use environment variables for configuration.
2. Have no complex setup requirements, e.g., where multiple applications need to be run together, or where we need to launch a browser, etc.

Always report to the user which samples were run and which were not, and why.

## Verifying a sample

Samples should be verified to ensure that they actually work as intended and that their output matches what is expected.
For each sample that is run, output should be produced that shows the result and explains the reasoning about what output
was expected, what was produced, and why it didn't match what the sample was expected to produce.

Steps to verify a sample:
1. Read the code for the sample
1. Check what environment variables are required for the sample
1. Check if each environment variable has been set
1. If there are any missing, give the user a list of missing environment variables to set and terminate
1. Summarize what the expected output of the sample should be
1. Run the sample
1. Show the user any output from the sample run as it gets produced, so that they can see the run progress
1. Check the output of the run against expectations
1. After running all requested samples, produce output for each sample that was verified:
  1. If expectations were matched, output the following:
     ```text
     [Sample Name] Succeeded
     ```
  1. If expectations were not matched, output the following:
     ```text
     [Sample Name] Failed
     Actual Output:
     [What the sample produced]
     Expected Output:
     [Explanation of what was expected and why the actual output didn't match expectations]
     ```

## Environment Variables

Most samples use environment variables to configure settings.

```csharp
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
```

To run a sample, the environment variables should be set first.
Before running a sample, check whether each environment variable in the sample has a value and
then give the user a list of environment variables to set.

You can provide the user some examples of how to set the variables like this:

```bash
export AZURE_OPENAI_ENDPOINT="https://my-openai-instance.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

To check if a variable has a value use e.g.:

```bash
echo $AZURE_OPENAI_ENDPOINT
```

## How to Run a Sample (General Pattern)

```bash
cd dotnet/samples/<category>/<sample-dir>
dotnet run
```

For multi-targeted projects (e.g., Durable console apps), specify the framework:

```bash
dotnet run --framework net10.0
```

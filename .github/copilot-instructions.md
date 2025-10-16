# GitHub Copilot Instructions

This repository contains both Python and C# code.
All python code resides under the `python/` directory.
All C# code resides under the `dotnet/` directory.

The purpose of the code is to provide a framework for building AI agents.

When contributing to this repository, please follow these guidelines:

## C# Code Guidelines

Here are some general guidelines that apply to all code.

- The top of all *.cs files should have a copyright notice: `// Copyright (c) Microsoft. All rights reserved.`
- All public methods and classes should have XML documentation comments.

### C# Sample Code Guidelines

Sample code is located in the `dotnet/samples` directory.

When adding a new sample, follow these steps:

- The sample should be a standalone .net project in one of the subdirectories of the samples directory.
- The directory name should be the same as the project name.
- The directory should contain a README.md file that explains what the sample does and how to run it.
- The README.md file should follow the same format as other samples.
- The csproj file should match the directory name.
- The csproj file should be configured in the same way as other samples.
- The project should preferably contain a single Program.cs file that contains all the sample code.
- The sample should be added to the solution file in the samples directory.
- The sample should be tested to ensure it works as expected.
- A reference to the new samples should be added to the README.md file in the parent directory of the new sample.

The sample code should follow these guidelines:

- Configuration settings should be read from environment variables, e.g. `var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");`.
- Environment variables should use upper snake_case naming convention.
- Secrets should not be hardcoded in the code or committed to the repository.
- The code should be well-documented with comments explaining the purpose of each step.
- The code should be simple and to the point, avoiding unnecessary complexity.
- Prefer inline literals over constants for values that are not reused. For example, use `new ChatClientAgent(chatClient, instructions: "You are a helpful assistant.")` instead of defining a constant for "instructions".
- Ensure that all private classes are sealed
- Use the Async suffix on the name of all async methods that return a Task or ValueTask.
- Prefer defining variables using types rather than var, to help users understand the types involved.
- Follow the patterns in the samples in the same directories where new samples are being added.
- The structure of the sample should be as follows:
  - The top of the Program.cs should have a copyright notice: `// Copyright (c) Microsoft. All rights reserved.`
  - Then add a comment describing what the sample is demonstrating.
  - Then add the necessary using statements.
  - Then add the main code logic.
  - Finally, add any helper methods or classes at the bottom of the file.

### C# Unit Test Guidelines

Unit tests are located in the `dotnet/tests` directory in projects with a `.UnitTests.csproj` suffix.

Unit tests should follow these guidelines:

- Use `this.` for accessing class members
- Add Arrange, Act and Assert comments for each test
- Ensure that all private classes, that are not subclassed, are sealed
- Use the Async suffix on the name of all async methods
- Use the Moq library for mocking objects where possible
- Validate that each test actually tests the target behavior, e.g. we should not have tests that creates a mock, calls the mock and then verifies that the mock was called, without the target code being involved. We also shouldn't have tests that test language features, e.g. something that the compiler would catch anyway.
- Avoid adding excessive comments to tests. Instead favour clear easy to understand code.
- Follow the patterns in the unit tests in the same project or classes to which new tests are being added

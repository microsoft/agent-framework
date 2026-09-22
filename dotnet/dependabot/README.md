# Dependabot NuGet discovery

This folder contains the NuGet entry point used by Dependabot.

Dependabot's NuGet updater expands solution files before resolving package updates. The developer solution in `dotnet/agent-framework-dotnet.slnx` includes the sample projects, and expanding those projects causes the updater to exceed its fixed execution timeout before it can open dependency update pull requests.

`agent-framework-dependabot.slnx` intentionally references only non-sample source and test projects. The referenced projects still live under `dotnet/src` and `dotnet/tests`, so MSBuild imports the central package management configuration from `dotnet/Directory.Packages.props` normally.

Do not add sample projects to this solution. If a new non-sample project should be covered by Dependabot NuGet updates, add it here.

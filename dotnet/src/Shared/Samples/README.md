# SampleEnvironemnt.cs

`SampleEnvironemnt.cs` defines a helper that overrides `System.Environment` class for a project.
This override version has an enhanced `GetEnvironmentVariable` method that prompts the user
to enter a value if the environment variable is not set.

Sample code is still fully copyable to another project. This override just allow for a simplified experience
for users who are new and just getting started.

This file is already included in all samples via `/dotnet/samples/Directory.Build.props`.

To explicitly use `SampleEnvironemnt.cs` outside of this repo, add the following to your `.csproj` file:

```xml
<ItemGroup>
  <Using Include="SampleHelpers.SampleEnvironment" Alias="Environment" />
</ItemGroup>

<ItemGroup>
  <Compile Include="$(MSBuildThisFileDirectory)\..\src\Shared\Samples\*.cs" LinkBase="" Visible="false" />
</ItemGroup>
```

# AG-UI Infrastructure Setup Implementation Plan

This document outlines the step-by-step implementation plan for setting up the infrastructure needed to support AG-UI (Agent-User Interaction) protocol in the Microsoft Agent Framework.

## Overview

Based on the Plan.md requirements and analysis of existing project patterns in the repository, this implementation plan covers creating the required projects and establishing the proper dependencies and configurations.

## Required Projects

The following projects need to be created as part of the infrastructure setup:

### Source Projects
1. **Microsoft.Agents.AI.AGUI** - Client library
2. **Microsoft.Agents.AI.Hosting.AGUI.AspNetCore** - Server library

### Test Projects  
3. **Microsoft.Agents.AI.AGUI.UnitTests** - Unit tests for client library
4. **Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests** - Unit tests for server library
5. **Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests** - Integration tests

## Implementation Steps

### Step 1: Create Client Library Project (Microsoft.Agents.AI.AGUI)

**Location**: `dotnet/src/Microsoft.Agents.AI.AGUI/`

**Files to create**:
- `Microsoft.Agents.AI.AGUI.csproj`
- `Shared/` directory (for shared AG-UI types)

**Project Configuration**:
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>$(ProjectsTargetFrameworks)</TargetFrameworks>
    <TargetFrameworks Condition="'$(Configuration)' == 'Debug'">$(ProjectsDebugTargetFrameworks)</TargetFrameworks>
    <VersionSuffix>preview</VersionSuffix>
  </PropertyGroup>

  <Import Project="$(RepoRoot)/dotnet/nuget/nuget-package.props" />

  <PropertyGroup>
    <InjectSharedThrow>true</InjectSharedThrow>
  </PropertyGroup>

  <PropertyGroup>
    <!-- NuGet Package Settings -->
    <Title>Microsoft Agent Framework AG-UI</Title>
    <Description>Provides Microsoft Agent Framework support for Agent-User Interaction (AG-UI) protocol client functionality.</Description>
  </PropertyGroup>

  <ItemGroup>
    <ProjectReference Include="..\Microsoft.Agents.AI.Abstractions\Microsoft.Agents.AI.Abstractions.csproj" />
  </ItemGroup>

  <ItemGroup>
    <PackageReference Include="System.Net.ServerSentEvents" />
    <PackageReference Include="Microsoft.Bcl.AsyncInterfaces" />
    <PackageReference Include="System.Text.Json" />
    <PackageReference Include="System.Threading.Channels" />
  </ItemGroup>

  <ItemGroup>
    <InternalsVisibleTo Include="Microsoft.Agents.AI.AGUI.UnitTests" />
    <InternalsVisibleTo Include="Microsoft.Agents.AI.Hosting.AGUI.AspNetCore" />
    <InternalsVisibleTo Include="Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests" />
  </ItemGroup>
</Project>
```

**Dependencies**:
- Microsoft.Agents.AI.Abstractions (for AIAgent base class)
- System.Net.ServerSentEvents (for SSE communication)
- Microsoft.Bcl.AsyncInterfaces (for async support)
- System.Text.Json (for JSON serialization)
- System.Threading.Channels (for streaming)

### Step 2: Create Server Library Project (Microsoft.Agents.AI.Hosting.AGUI.AspNetCore)

**Location**: `dotnet/src/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore/`

**Files to create**:
- `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.csproj`

**Project Configuration**:
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>$(ProjectsCoreTargetFrameworks)</TargetFrameworks>
    <TargetFrameworks Condition="'$(Configuration)' == 'Debug'">$(ProjectsDebugCoreTargetFrameworks)</TargetFrameworks>
    <RootNamespace>Microsoft.Agents.AI.Hosting.AGUI.AspNetCore</RootNamespace>
    <VersionSuffix>preview</VersionSuffix>
  </PropertyGroup>

  <Import Project="$(RepoRoot)/dotnet/nuget/nuget-package.props" />

  <PropertyGroup>
    <!-- NuGet Package Settings -->
    <Title>Microsoft Agent Framework Hosting AG-UI ASP.NET Core</Title>
    <Description>Provides Microsoft Agent Framework support for hosting AG-UI agents in an ASP.NET Core context.</Description>
  </PropertyGroup>

  <ItemGroup>
    <ProjectReference Include="..\Microsoft.Agents.AI.AGUI\Microsoft.Agents.AI.AGUI.csproj" />
    <ProjectReference Include="..\Microsoft.Agents.AI.Hosting\Microsoft.Agents.AI.Hosting.csproj" />
  </ItemGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" />
    <PackageReference Include="System.Net.ServerSentEvents" />
    <PackageReference Include="Microsoft.Bcl.AsyncInterfaces" />
    <PackageReference Include="System.Text.Json" />
  </ItemGroup>

  <!-- Include shared AG-UI types from client library -->
  <ItemGroup>
    <Compile Include="..\Microsoft.Agents.AI.AGUI\Shared\**\*.cs" LinkBase="Shared" />
  </ItemGroup>

  <ItemGroup>
    <InternalsVisibleTo Include="Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests" />
    <InternalsVisibleTo Include="Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests" />
  </ItemGroup>
</Project>
```

**Dependencies**:
- Microsoft.Agents.AI.AGUI (for shared types via source inclusion)
- Microsoft.Agents.AI.Hosting (for hosting infrastructure)  
- Microsoft.AspNetCore.OpenApi (for API documentation)
- System.Net.ServerSentEvents (for SSE communication)

### Step 3: Create Client Unit Test Project

**Location**: `dotnet/tests/Microsoft.Agents.AI.AGUI.UnitTests/`

**Files to create**:
- `Microsoft.Agents.AI.AGUI.UnitTests.csproj`

**Project Configuration**:
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>$(ProjectsTargetFrameworks)</TargetFrameworks>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="System.Net.ServerSentEvents" />
    <PackageReference Include="Microsoft.Bcl.AsyncInterfaces" />
    <PackageReference Include="System.Text.Json" />
    <PackageReference Include="FluentAssertions" />
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="..\..\src\Microsoft.Agents.AI.AGUI\Microsoft.Agents.AI.AGUI.csproj" />
  </ItemGroup>
</Project>
```

### Step 4: Create Server Unit Test Project

**Location**: `dotnet/tests/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests/`

**Files to create**:
- `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests.csproj`

**Project Configuration**:
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>$(ProjectsCoreTargetFrameworks)</TargetFrameworks>
    <TargetFrameworks Condition="'$(Configuration)' == 'Debug'">$(ProjectsDebugCoreTargetFrameworks)</TargetFrameworks>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" />
    <PackageReference Include="System.Net.ServerSentEvents" />
    <PackageReference Include="Microsoft.Bcl.AsyncInterfaces" />
    <PackageReference Include="System.Text.Json" />
    <PackageReference Include="FluentAssertions" />
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="..\..\src\Microsoft.Agents.AI.Hosting.AGUI.AspNetCore\Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.csproj" />
  </ItemGroup>
</Project>
```

### Step 5: Create Integration Test Project

**Location**: `dotnet/tests/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests/`

**Files to create**:
- `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.csproj`

**Project Configuration**:
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFrameworks>$(ProjectsTargetFrameworks)</TargetFrameworks>
  </PropertyGroup>

  <PropertyGroup>
    <InjectSharedIntegrationTestCode>true</InjectSharedIntegrationTestCode>
    <InjectSharedBuildTestCode>true</InjectSharedBuildTestCode>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.AspNetCore.Mvc.Testing" />
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" />
    <PackageReference Include="System.Net.ServerSentEvents" />
    <PackageReference Include="Microsoft.Bcl.AsyncInterfaces" />
    <PackageReference Include="System.Text.Json" />
    <PackageReference Include="FluentAssertions" />
    <PackageReference Include="Microsoft.Extensions.Configuration.UserSecrets" />
    <PackageReference Include="Microsoft.Extensions.Configuration.EnvironmentVariables" />
    <PackageReference Include="Azure.Identity" />
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="..\..\src\Microsoft.Agents.AI.Hosting.AGUI.AspNetCore\Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.csproj" />
    <ProjectReference Include="..\..\src\Microsoft.Agents.AI.AGUI\Microsoft.Agents.AI.AGUI.csproj" />
  </ItemGroup>
</Project>
```

### Step 6: Update Solution File

**File**: `dotnet/agent-framework-dotnet.slnx`

**Add the following entries**:

Under `/src/` folder:
```xml
<Project Path="src/Microsoft.Agents.AI.AGUI/Microsoft.Agents.AI.AGUI.csproj" />
<Project Path="src/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.csproj" />
```

Under `/Tests/UnitTests/` folder:
```xml
<Project Path="tests/Microsoft.Agents.AI.AGUI.UnitTests/Microsoft.Agents.AI.AGUI.UnitTests.csproj" />
<Project Path="tests/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests.csproj" />
```

Under `/Tests/IntegrationTests/` folder:
```xml
<Project Path="tests/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests/Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests.csproj" />
```

## Key Architectural Decisions

### 1. Shared Types Strategy
- AG-UI protocol types will be defined in `Microsoft.Agents.AI.AGUI/Shared/` directory
- Server project will reference these types via `<Compile Include>` to avoid creating a separate shared library
- All AG-UI types will be `internal` to prevent public API exposure

### 2. Dependency Management
- Client library depends on `Microsoft.Agents.AI.Abstractions` for base AIAgent functionality
- Server library depends on both client library and `Microsoft.Agents.AI.Hosting`
- All projects use centralized package management via `Directory.Packages.props`

### 3. Target Framework Strategy
- Client library: Full framework support (`$(ProjectsTargetFrameworks)`) including .NET Standard 2.0 and .NET Framework 4.7.2
- Server library: .NET Core only (`$(ProjectsCoreTargetFrameworks)`) since ASP.NET Core is required
- Test projects: Follow respective library targeting

### 4. InternalsVisibleTo Configuration
- Strategic visibility between projects for testing and shared type access
- Client library exposes internals to server library and test projects
- Server library exposes internals to its test projects

### 5. Package References
- Standard Microsoft.Extensions.AI ecosystem packages
- System.Net.ServerSentEvents for real-time communication
- System.Text.Json for serialization
- FluentAssertions for test readability

## Validation Steps

After creating all projects:

1. **Build Verification**: Ensure all projects build successfully
   ```powershell
   dotnet build dotnet/agent-framework-dotnet.slnx
   ```

2. **Package Restoration**: Verify all packages restore correctly
   ```powershell
   dotnet restore dotnet/agent-framework-dotnet.slnx
   ```

3. **Project References**: Confirm all project references resolve properly

4. **Solution Structure**: Verify projects appear correctly in solution explorer

5. **Test Framework**: Ensure test projects can discover and run (even with empty tests)
   ```powershell
   dotnet test dotnet/agent-framework-dotnet.slnx --filter "FullyQualifiedName~AGUI"
   ```

## Next Steps

Once the infrastructure is established:

1. **Define Core AG-UI Types**: Create shared protocol types in `Microsoft.Agents.AI.AGUI/Shared/`
2. **Implement AGUIAgent**: Create the client-side agent implementation
3. **Implement Server Mapping**: Create the `MapAGUIAgent` extension method for ASP.NET Core
4. **Add Basic Integration Test**: Implement the first end-to-end scenario
5. **Iterate with TDD**: Follow the BDD approach outlined in the plan

This infrastructure setup provides a solid foundation following repository patterns and best practices while supporting the AG-UI protocol requirements.

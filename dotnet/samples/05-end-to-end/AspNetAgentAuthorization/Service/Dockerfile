FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /repo

# Copy solution-level files for restore
COPY Directory.Build.props Directory.Build.targets Directory.Packages.props global.json nuget.config ./
COPY eng/ eng/
COPY nuget/ nuget/
COPY src/Shared/ src/Shared/
COPY samples/Directory.Build.props samples/

# Create sentinel file so $(RepoRoot) resolves correctly inside the container.
# RepoRoot is the parent of the dir containing CODE_OF_CONDUCT.md,
# and src projects import $(RepoRoot)/dotnet/nuget/nuget-package.props.
RUN touch /CODE_OF_CONDUCT.md && mkdir -p /dotnet/nuget && cp /repo/nuget/* /dotnet/nuget/

# Copy project files for restore
COPY src/Microsoft.Agents.AI.Abstractions/Microsoft.Agents.AI.Abstractions.csproj src/Microsoft.Agents.AI.Abstractions/
COPY src/Microsoft.Agents.AI/Microsoft.Agents.AI.csproj src/Microsoft.Agents.AI/
COPY src/Microsoft.Agents.AI.OpenAI/Microsoft.Agents.AI.OpenAI.csproj src/Microsoft.Agents.AI.OpenAI/
COPY samples/05-end-to-end/AspNetAgentAuthorization/Service/Service.csproj samples/05-end-to-end/AspNetAgentAuthorization/Service/

RUN dotnet restore samples/05-end-to-end/AspNetAgentAuthorization/Service/Service.csproj -p:TargetFramework=net10.0 -p:TreatWarningsAsErrors=false

# Copy everything and build
COPY src/ src/
COPY samples/05-end-to-end/AspNetAgentAuthorization/Service/ samples/05-end-to-end/AspNetAgentAuthorization/Service/
RUN dotnet publish samples/05-end-to-end/AspNetAgentAuthorization/Service/Service.csproj -c Release -f net10.0 -o /app -p:TreatWarningsAsErrors=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
ENV ASPNETCORE_URLS=http://+:5001
EXPOSE 5001
ENTRYPOINT ["dotnet", "Service.dll"]

# Dockerfile for end-users consuming the Agent Framework via NuGet packages.
#
# This Dockerfile performs a full `dotnet restore` and `dotnet publish` inside the container,
# which only succeeds when the project references its dependencies via PackageReference (see the
# commented-out section in HostedToolboxMcpSkills.csproj). Contributors building from the
# agent-framework repository source must use Dockerfile.contributor instead because
# ProjectReference dependencies live outside this folder and cannot be restored from inside
# this build context.
#
# Use the official .NET 10.0 ASP.NET runtime as a parent image
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS base
WORKDIR /app

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet restore
RUN dotnet publish -c Release -o /app/publish

# Final stage
FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
EXPOSE 8088
ENV ASPNETCORE_URLS=http://+:8088
ENTRYPOINT ["dotnet", "HostedToolboxMcpSkills.dll"]

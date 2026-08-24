# Foundry builds this image and runs it as the hosted agent. The build restores and publishes the
# project inside the container, so a contributor feed dropped into this folder (local-feed/ plus
# nuget.config) is picked up by the `dotnet restore` below without any change here.
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet restore
RUN dotnet publish -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .

# Foundry probes port 8088 for readiness. The .NET base image defaults ASPNETCORE_URLS to port 80,
# so without this the probe never succeeds and every invoke fails with HTTP 424 session_not_ready.
EXPOSE 8088
ENV ASPNETCORE_URLS=http://+:8088

ENTRYPOINT ["dotnet", "HostedChatClientAgentDocker.dll"]

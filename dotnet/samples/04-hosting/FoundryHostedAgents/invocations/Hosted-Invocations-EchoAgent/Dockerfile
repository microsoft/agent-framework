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
ENTRYPOINT ["dotnet", "HostedInvocationsEchoAgent.dll"]

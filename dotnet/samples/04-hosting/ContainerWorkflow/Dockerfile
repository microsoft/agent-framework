FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish dotnet/samples/04-hosting/ContainerWorkflow/ContainerWorkflow.csproj \
    -c Release -f net10.0 -o /app/publish --tl:off

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish .
USER $APP_UID
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "ContainerWorkflow.dll"]

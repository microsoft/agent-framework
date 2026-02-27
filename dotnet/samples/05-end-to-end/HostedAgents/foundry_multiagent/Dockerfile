# Build the application
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src

# Copy project files for dependency resolution
COPY *.csproj* .
RUN dotnet restore dotnetmultiagent.csproj

# Copy files from the current directory on the host to the working directory in the container
COPY . .

RUN dotnet publish -c Release -o /app -p:AssemblyName=app

# Run the application
FROM mcr.microsoft.com/dotnet/aspnet:9.0
WORKDIR /app

# Copy everything needed to run the app from the "build" stage.
COPY --from=build /app .

EXPOSE 8088
ENTRYPOINT ["dotnet", "app.dll"]

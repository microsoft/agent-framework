FROM mcr.microsoft.com/dotnet/aspnet:10.0-alpine
WORKDIR /app
COPY out/ .
EXPOSE 8088
ENV ASPNETCORE_URLS=http://+:8088
ENTRYPOINT ["dotnet", "HostedHarnessDataProcessing.dll"]

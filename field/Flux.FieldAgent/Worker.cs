using Microsoft.Extensions.Options;
using System.Text.Json;

namespace Flux.FieldAgent;

public sealed class Worker(
    ILogger<Worker> logger,
    IOptions<FieldAgentOptions> options,
    FieldOpcServerHost serverHost) : BackgroundService
{
    private static readonly HttpClient HttpClient = new();

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var selectedOptions = options.Value;
        logger.LogInformation(
            "Flux Field Agent starting endpoint={EndpointUrl} config={ConfigUrl} opcApplicationType={ApplicationType}",
            selectedOptions.EndpointUrl,
            selectedOptions.ConfigUrl,
            OpcStackProbe.ServerApplicationType());

        var config = await LoadConfig(selectedOptions, stoppingToken);
        LogConfigSummary(config);
        await serverHost.StartAsync(config, selectedOptions, stoppingToken);

        while (!stoppingToken.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromSeconds(Math.Max(selectedOptions.PollSeconds, 1)), stoppingToken);
        }
    }

    public override Task StopAsync(CancellationToken cancellationToken)
    {
        serverHost.Stop();
        return base.StopAsync(cancellationToken);
    }

    private static async Task<FieldConfig> LoadConfig(FieldAgentOptions options, CancellationToken stoppingToken)
    {
        if (!string.IsNullOrWhiteSpace(options.ConfigPath) && File.Exists(options.ConfigPath))
        {
            await using var fileStream = File.OpenRead(options.ConfigPath);
            return await JsonSerializer.DeserializeAsync<FieldConfig>(fileStream, cancellationToken: stoppingToken)
                ?? new FieldConfig();
        }

        using var response = await HttpClient.GetAsync(options.ConfigUrl, stoppingToken);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(stoppingToken);
        return await JsonSerializer.DeserializeAsync<FieldConfig>(stream, cancellationToken: stoppingToken)
            ?? new FieldConfig();
    }

    private void LogConfigSummary(FieldConfig config)
    {
        var endpointCount = config.Endpoints.Count;
        var deviceCount = config.Endpoints.Sum(endpoint => endpoint.Devices.Count);
        var tagCount = config.Endpoints.Sum(endpoint => endpoint.Devices.Sum(device => device.Tags.Count));

        logger.LogInformation(
            "Flux Field config loaded endpoints={EndpointCount} devices={DeviceCount} tags={TagCount}",
            endpointCount,
            deviceCount,
            tagCount);
        if (endpointCount == 0 || tagCount == 0)
        {
            logger.LogWarning("Flux Field config has no endpoints or tags; OPC UA server will expose an empty FluxField folder");
        }
    }
}

namespace Flux.Agent;

public sealed class Worker(ILogger<Worker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        logger.LogInformation("Flux Agent starting");

        while (!stoppingToken.IsCancellationRequested)
        {
            logger.LogInformation("Flux Agent heartbeat at {Timestamp}", DateTimeOffset.UtcNow);
            await Task.Delay(TimeSpan.FromSeconds(5), stoppingToken);
        }
    }
}

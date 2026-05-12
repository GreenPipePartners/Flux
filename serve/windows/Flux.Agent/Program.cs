using Flux.Agent;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddWindowsService(options =>
{
    options.ServiceName = "Flux Agent";
});

builder.Services.AddHostedService<Worker>();

var host = builder.Build();
host.Run();

using Flux.FieldAgent;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddWindowsService(options =>
{
    options.ServiceName = "Flux Field Agent";
});
builder.Services.AddSystemd();
builder.Services.Configure<FieldAgentOptions>(builder.Configuration.GetSection("FluxField"));
builder.Services.AddSingleton<FieldOpcServerHost>();
builder.Services.AddHostedService<Worker>();

var host = builder.Build();
host.Run();

namespace Flux.FieldAgent;

public sealed class FieldAgentOptions
{
    public string ConfigUrl { get; set; } = "http://localhost:8000/field/config.json";
    public string? ConfigPath { get; set; }
    public string EndpointUrl { get; set; } = "opc.tcp://0.0.0.0:4840/flux/field";
    public int PollSeconds { get; set; } = 5;
    public string CertificateStorePath { get; set; } = "pki";
}

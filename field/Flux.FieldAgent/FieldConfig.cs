using System.Text.Json.Serialization;

namespace Flux.FieldAgent;

public sealed class FieldConfig
{
    [JsonPropertyName("endpoints")]
    public List<FieldEndpointConfig> Endpoints { get; set; } = [];
}

public sealed class FieldEndpointConfig
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("endpoint_url")]
    public string EndpointUrl { get; set; } = "";

    [JsonPropertyName("namespace_uri")]
    public string NamespaceUri { get; set; } = "";

    [JsonPropertyName("devices")]
    public List<FieldDeviceConfig> Devices { get; set; } = [];
}

public sealed class FieldDeviceConfig
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("device_type")]
    public string DeviceType { get; set; } = "";

    [JsonPropertyName("browse_path")]
    public string BrowsePath { get; set; } = "";

    [JsonPropertyName("tags")]
    public List<FieldTagConfig> Tags { get; set; } = [];
}

public sealed class FieldTagConfig
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("node_id")]
    public string NodeId { get; set; } = "";

    [JsonPropertyName("opc_item_path")]
    public string OpcItemPath { get; set; } = "";

    [JsonPropertyName("data_type")]
    public string DataType { get; set; } = "";

    [JsonPropertyName("update_rate_ms")]
    public int UpdateRateMs { get; set; } = 1000;

    [JsonPropertyName("simulation_type")]
    public string SimulationType { get; set; } = "static";

    [JsonPropertyName("min_value")]
    public double? MinValue { get; set; }

    [JsonPropertyName("max_value")]
    public double? MaxValue { get; set; }

    [JsonPropertyName("variance")]
    public double Variance { get; set; }

    [JsonPropertyName("initial_value")]
    public string InitialValue { get; set; } = "";
}

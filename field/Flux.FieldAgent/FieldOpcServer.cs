using Opc.Ua;
using Opc.Ua.Server;

namespace Flux.FieldAgent;

public sealed class FieldOpcServer(FieldConfig config) : StandardServer
{
    protected override MasterNodeManager CreateMasterNodeManager(
        IServerInternal server,
        ApplicationConfiguration configuration)
    {
        var nodeManagers = new List<INodeManager>
        {
            new FieldNodeManager(server, configuration, config)
        };
        return new MasterNodeManager(server, configuration, null, nodeManagers.ToArray());
    }

    protected override ServerProperties LoadServerProperties()
    {
        return new ServerProperties
        {
            ManufacturerName = "Flux",
            ProductName = "Flux Field OPC UA Simulator",
            ProductUri = "urn:flux:field",
            SoftwareVersion = typeof(FieldOpcServer).Assembly.GetName().Version?.ToString() ?? "0.1.0",
            BuildNumber = "dev",
            BuildDate = DateTime.UtcNow,
        };
    }
}

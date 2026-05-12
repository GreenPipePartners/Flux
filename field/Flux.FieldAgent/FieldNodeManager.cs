using Opc.Ua;
using Opc.Ua.Server;

namespace Flux.FieldAgent;

public sealed class FieldNodeManager : CustomNodeManager2
{
    private readonly FieldConfig config;
    private readonly List<SimulatedVariable> variables = [];
    private Timer? updateTimer;
    private ushort namespaceIndex;

    public FieldNodeManager(
        IServerInternal server,
        ApplicationConfiguration configuration,
        FieldConfig config)
        : base(server, configuration, server.Telemetry.CreateLogger<FieldNodeManager>())
    {
        this.config = config;
        NamespaceUris = [.. config.Endpoints.Select(endpoint => endpoint.NamespaceUri).Where(uri => !string.IsNullOrWhiteSpace(uri)).DefaultIfEmpty("urn:flux:field:sim")];
        SystemContext.NodeIdFactory = this;
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            updateTimer?.Dispose();
            updateTimer = null;
        }
        base.Dispose(disposing);
    }

    public override NodeId New(ISystemContext context, NodeState node)
    {
        if (node.NodeId is not null && !NodeId.IsNull(node.NodeId))
        {
            return node.NodeId;
        }
        var name = node.SymbolicName ?? node.DisplayName.Text ?? Guid.NewGuid().ToString("N");
        return new NodeId(name, namespaceIndex);
    }

    public override void CreateAddressSpace(IDictionary<NodeId, IList<IReference>> externalReferences)
    {
        lock (Lock)
        {
            var namespaceUri = config.Endpoints.FirstOrDefault()?.NamespaceUri ?? "urn:flux:field:sim";
            namespaceIndex = Server.NamespaceUris.GetIndexOrAppend(namespaceUri);

            if (!externalReferences.TryGetValue(ObjectIds.ObjectsFolder, out var references))
            {
                references = [];
                externalReferences[ObjectIds.ObjectsFolder] = references;
            }

            var root = CreateFolder(null, "FluxField", "FluxField");
            root.AddReference(ReferenceTypeIds.Organizes, true, ObjectIds.ObjectsFolder);
            references.Add(new NodeStateReference(ReferenceTypeIds.Organizes, false, root.NodeId));
            AddPredefinedNode(SystemContext, root);

            foreach (var endpoint in config.Endpoints)
            {
                foreach (var device in endpoint.Devices)
                {
                    var deviceFolder = CreateFolder(root, device.Name, device.Name);
                    AddPredefinedNode(SystemContext, deviceFolder);
                    foreach (var tag in device.Tags)
                    {
                        var variable = CreateVariable(deviceFolder, tag);
                        AddPredefinedNode(SystemContext, variable);
                        variables.Add(new SimulatedVariable(variable, tag));
                    }
                }
            }

            updateTimer = new Timer(UpdateVariables, null, TimeSpan.Zero, TimeSpan.FromMilliseconds(100));
        }
    }

    private FolderState CreateFolder(NodeState? parent, string path, string name)
    {
        var folder = new FolderState(parent)
        {
            SymbolicName = name,
            ReferenceTypeId = ReferenceTypeIds.Organizes,
            TypeDefinitionId = ObjectTypeIds.FolderType,
            NodeId = new NodeId(path, namespaceIndex),
            BrowseName = new QualifiedName(name, namespaceIndex),
            DisplayName = name,
            WriteMask = AttributeWriteMask.None,
            UserWriteMask = AttributeWriteMask.None,
            EventNotifier = EventNotifiers.None,
        };
        parent?.AddChild(folder);
        return folder;
    }

    private BaseDataVariableState CreateVariable(NodeState parent, FieldTagConfig tag)
    {
        var variable = new BaseDataVariableState(parent)
        {
            SymbolicName = tag.Name,
            ReferenceTypeId = ReferenceTypeIds.Organizes,
            TypeDefinitionId = VariableTypeIds.BaseDataVariableType,
            NodeId = ParseConfiguredNodeId(tag),
            BrowseName = new QualifiedName(tag.Name, namespaceIndex),
            DisplayName = tag.Name,
            WriteMask = AttributeWriteMask.None,
            UserWriteMask = AttributeWriteMask.None,
            DataType = DataTypeFor(tag.DataType),
            ValueRank = ValueRanks.Scalar,
            AccessLevel = AccessLevels.CurrentRead,
            UserAccessLevel = AccessLevels.CurrentRead,
            Historizing = false,
            MinimumSamplingInterval = Math.Max(tag.UpdateRateMs, 100),
            StatusCode = StatusCodes.Good,
            Timestamp = DateTime.UtcNow,
            Value = SimulatedValueGenerator.InitialValue(tag),
        };
        parent.AddChild(variable);
        return variable;
    }

    private NodeId ParseConfiguredNodeId(FieldTagConfig tag)
    {
        if (NodeId.TryParse(tag.NodeId, out var nodeId))
        {
            return new NodeId(nodeId.Identifier, namespaceIndex);
        }
        return new NodeId(tag.NodeId, namespaceIndex);
    }

    private static NodeId DataTypeFor(string dataType)
    {
        return dataType switch
        {
            "bool" => DataTypeIds.Boolean,
            "int" => DataTypeIds.Int32,
            "float" => DataTypeIds.Double,
            "string" => DataTypeIds.String,
            _ => DataTypeIds.String,
        };
    }

    private void UpdateVariables(object? state)
    {
        lock (Lock)
        {
            var now = DateTime.UtcNow;
            foreach (var variable in variables)
            {
                if (now < variable.NextUpdateUtc)
                {
                    continue;
                }
                variable.Node.Value = SimulatedValueGenerator.NextValue(variable.Tag, variable.SampleIndex);
                variable.Node.Timestamp = now;
                variable.Node.StatusCode = StatusCodes.Good;
                variable.Node.ClearChangeMasks(SystemContext, false);
                variable.SampleIndex++;
                variable.NextUpdateUtc = now.AddMilliseconds(Math.Max(variable.Tag.UpdateRateMs, 100));
            }
        }
    }
}

internal sealed class SimulatedVariable(BaseDataVariableState node, FieldTagConfig tag)
{
    public BaseDataVariableState Node { get; } = node;
    public FieldTagConfig Tag { get; } = tag;
    public long SampleIndex { get; set; }
    public DateTime NextUpdateUtc { get; set; } = DateTime.UtcNow;
}

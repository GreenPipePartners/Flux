namespace Flux.FieldAgent;

public static class SimulatedValueGenerator
{
    public static object InitialValue(FieldTagConfig tag)
    {
        if (!string.IsNullOrWhiteSpace(tag.InitialValue))
        {
            return tag.DataType switch
            {
                "bool" => bool.TryParse(tag.InitialValue, out var boolValue) && boolValue,
                "int" => int.TryParse(tag.InitialValue, out var intValue) ? intValue : 0,
                "float" => double.TryParse(tag.InitialValue, out var doubleValue) ? doubleValue : 0.0,
                _ => tag.InitialValue,
            };
        }
        return tag.DataType switch
        {
            "bool" => false,
            "int" => (int)(tag.MinValue ?? 0),
            "float" => tag.MinValue ?? 0.0,
            _ => string.Empty,
        };
    }

    public static object NextValue(FieldTagConfig tag, long sampleIndex)
    {
        return tag.DataType switch
        {
            "bool" => BoolValue(tag, sampleIndex),
            "int" => IntValue(tag, sampleIndex),
            "float" => FloatValue(tag, sampleIndex),
            "string" => StringValue(tag, sampleIndex),
            _ => StringValue(tag, sampleIndex),
        };
    }

    private static bool BoolValue(FieldTagConfig tag, long sampleIndex)
    {
        return tag.SimulationType == "static" ? Convert.ToBoolean(InitialValue(tag)) : sampleIndex % 2 == 1;
    }

    private static int IntValue(FieldTagConfig tag, long sampleIndex)
    {
        var min = (int)(tag.MinValue ?? 0);
        var max = (int)(tag.MaxValue ?? 100);
        if (max <= min)
        {
            max = min + 1;
        }
        if (tag.SimulationType == "static")
        {
            return Convert.ToInt32(InitialValue(tag));
        }
        return min + (int)(sampleIndex % (max - min + 1));
    }

    private static double FloatValue(FieldTagConfig tag, long sampleIndex)
    {
        var min = tag.MinValue ?? 0.0;
        var max = tag.MaxValue ?? 100.0;
        if (max <= min)
        {
            max = min + 1.0;
        }
        if (tag.SimulationType == "static")
        {
            return Convert.ToDouble(InitialValue(tag));
        }
        var midpoint = min + ((max - min) / 2.0);
        var amplitude = (max - min) / 2.0;
        var wave = Math.Sin(sampleIndex / 10.0) * amplitude;
        var variance = tag.Variance == 0 ? 0 : Math.Sin(sampleIndex * 1.7) * tag.Variance;
        return Math.Clamp(midpoint + wave + variance, min, max);
    }

    private static string StringValue(FieldTagConfig tag, long sampleIndex)
    {
        var prefix = string.IsNullOrWhiteSpace(tag.InitialValue) ? tag.Name : tag.InitialValue;
        return tag.SimulationType == "static" ? prefix : $"{prefix}-{sampleIndex}";
    }
}

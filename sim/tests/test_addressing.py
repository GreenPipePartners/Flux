from flux_sim.addressing import parse_address


def test_logix_address_strategy_preserves_local_colon_path():
    address = parse_address("logix", "ns=2;s=PLC_01.Local:1:I.Data.0")

    assert address["device"] == "PLC_01"
    assert address["symbol"] == "Local:1:I.Data.0"
    assert address["scope"] == "Local"
    assert address["local_member"] == "1:I.Data.0"


def test_acm_address_strategy_extracts_device_and_member():
    address = parse_address("acm", "ns=2;s=RTU_01.40001F")

    assert address == {"raw": "ns=2;s=RTU_01.40001F", "device": "RTU_01", "member": "40001F"}


def test_modbus_address_strategy_extracts_register():
    address = parse_address("modbus", "ns=2;s=BR05_30_Murphy.40001")

    assert address["device"] == "BR05_30_Murphy"
    assert address["register"] == "40001"


def test_unknown_strategy_falls_back_to_generic():
    address = parse_address("unknown", "ns=2;s=Device.Tag")

    assert address["device"] == "Device"
    assert address["member"] == "Tag"

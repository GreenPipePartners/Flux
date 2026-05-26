import json
import os
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import TestCase

from flux.base.field_config import single_device_endpoint_config
from flux.base.models import (
    Device,
    Tag,
)
from flux.sim.models import DeviceConfig, FieldEndpoint, SimDriver, TagConfig, TagNode, TagProvider
from flux.sim.tag_data_ingest import ingest_live_tag_data_catalog, ingest_tag_data_catalog


REAL_TAG_DATA_ACCEPTANCE_ENV = "FLUX_ACCEPT_REAL_TAG_DATA"


class TagDataIngestTests(TestCase):
    def test_ingest_tag_data_catalog_imports_provider_devices_and_tags(self):
        with catalog_files() as (devices_path, tags_path):
            result = ingest_tag_data_catalog(provider_name="Tag_02", devices_path=devices_path, tags_path=tags_path)

        self.assertEqual(result.device_count, 2)
        self.assertEqual(result.tag_count, 3)
        self.assertEqual(result.unknown_device_count, 0)
        self.assertTrue(TagProvider.objects.filter(name="Tag_02").exists())
        self.assertEqual(TagProvider.objects.get(name="Tag_02").sim_server.name, "Flux sim OPC-UA Server")
        self.assertTrue(TagNode.objects.filter(provider__name="Tag_02", path="Area/RTU_01/PV").exists())
        self.assertEqual(SimDriver.objects.get(key="opc_ua").strategy_key, "acm")
        self.assertEqual(Device.objects.filter(namespace="provider:Tag_02").count(), 2)
        self.assertEqual(Tag.objects.filter(provider="Tag_02").count(), 3)
        self.assertEqual(DeviceConfig.objects.filter(source_provider__name="Tag_02").count(), 2)
        self.assertEqual(TagConfig.objects.filter(base_tag__provider="Tag_02", materialized=False).count(), 3)

    def test_ingest_tag_data_catalog_assigns_acm_provider_to_distinct_sim_server(self):
        with catalog_files(opc_server="ACM_02") as (devices_path, tags_path):
            ingest_tag_data_catalog(provider_name="Tag_02", devices_path=devices_path, tags_path=tags_path)

        provider = TagProvider.objects.get(name="Tag_02")

        self.assertEqual(provider.sim_server.name, "Flux sim ACM_02 Server")

    def test_ingest_tag_data_catalog_maps_ignition_opc_server_to_default_sim_server(self):
        with catalog_files(opc_server="Ignition OPC UA Server") as (devices_path, tags_path):
            ingest_tag_data_catalog(provider_name="Tag_05", devices_path=devices_path, tags_path=tags_path)

        provider = TagProvider.objects.get(name="Tag_05")

        self.assertEqual(provider.sim_server.name, "Flux sim OPC-UA Server")
        logix_tag = TagConfig.objects.get(base_tag__provider="Tag_05", source_path="Area/Standalone")
        self.assertEqual(logix_tag.device.name, "PLC_01")
        self.assertEqual(logix_tag.address_strategy, "logix")
        self.assertEqual(logix_tag.address["local_member"], "1:I.Data.0")

    def test_ingest_tag_data_catalog_is_idempotent(self):
        with catalog_files() as (devices_path, tags_path):
            ingest_tag_data_catalog(provider_name="Tag_02", devices_path=devices_path, tags_path=tags_path)
            ingest_tag_data_catalog(provider_name="Tag_02", devices_path=devices_path, tags_path=tags_path)

        self.assertEqual(TagProvider.objects.filter(name="Tag_02").count(), 1)
        self.assertEqual(DeviceConfig.objects.filter(source_provider__name="Tag_02").count(), 2)
        self.assertEqual(TagConfig.objects.filter(base_tag__provider="Tag_02", materialized=False).count(), 3)

    def test_import_tag_data_catalog_command_reports_counts(self):
        with catalog_files() as (devices_path, tags_path):
            call_command("import_tag_data_catalog", "Tag_02", "--devices", str(devices_path), "--tags", str(tags_path))

        self.assertEqual(TagConfig.objects.filter(base_tag__provider="Tag_02", materialized=False).count(), 3)


class BoundedRealTagDataMaterializationTests(TestCase):
    def test_real_tag_02_and_tag_05_subsets_materialize_deterministic_field_configs(self):
        cases = [
            RealTagDataSubset(
                provider="Tag_02",
                devices=(
                    "ACM_02\tOPC UA\ta month\tCONNECTED\tServerClient\n"
                    "BR05_30_Murphy\tModbusTcp\t\n"
                ),
                tags=tag_02_subset_provider_export(),
                expected={
                    "server": "Flux sim ACM_02 Server",
                    "ACM_02": {
                        "device_type": "OPC UA",
                        "tags": [
                            ("FlowRate", Tag.DataType.FLOAT),
                            ("RunStatus", Tag.DataType.BOOL),
                        ],
                    },
                    "BR05_30_Murphy": {
                        "device_type": "ModbusTcp",
                        "tags": [("Pressure", Tag.DataType.FLOAT)],
                    },
                },
            ),
            RealTagDataSubset(
                provider="Tag_05",
                devices=(
                    "AB_CGF02\tControlLogix\tConnected: Protocol: EIP - Run Mode\t\n"
                    "CGF04_EPOD\tModbusTcp\tConnected\t\n"
                ),
                tags=tag_05_subset_provider_export(),
                expected={
                    "server": "Flux sim OPC-UA Server",
                    "AB_CGF02": {
                        "device_type": "ControlLogix",
                        "tags": [
                            ("Local_Int", Tag.DataType.INT),
                            ("RunStatus", Tag.DataType.BOOL),
                        ],
                    },
                    "CGF04_EPOD": {
                        "device_type": "ModbusTcp",
                        "tags": [("BusVoltage", Tag.DataType.FLOAT)],
                    },
                },
            ),
        ]

        with real_tag_data_subset_files(cases) as paths_by_provider:
            for case in cases:
                with self.subTest(provider=case.provider):
                    devices_path, tags_path = paths_by_provider[case.provider]
                    call_command(
                        "import_tag_data_catalog",
                        case.provider,
                        "--devices",
                        str(devices_path),
                        "--tags",
                        str(tags_path),
                        "--skip-raw-config",
                    )
                    call_command("materialize_sim_field_config", "--provider", case.provider)

                    self.assertEqual(DeviceConfig.objects.filter(source_provider__name=case.provider).count(), 2)
                    self.assertEqual(
                        TagConfig.objects.filter(base_tag__provider=case.provider, materialized=True).count(), 3
                    )
                    self.assertEqual(
                        FieldEndpoint.objects.filter(sim_device_configs__browse_path=case.provider)
                        .distinct()
                        .count(),
                        1,
                    )

                    for device_name, expected in case.expected.items():
                        if device_name == "server":
                            continue
                        field_device = DeviceConfig.objects.get(
                            browse_path=case.provider, base_device__name=device_name
                        )
                        config = single_device_endpoint_config(field_device)
                        device_config = config["devices"][0]
                        self.assertEqual(config["name"], case.expected["server"])
                        self.assertEqual(device_config["name"], device_name)
                        self.assertEqual(device_config["device_type"], expected["device_type"])
                        self.assertEqual(device_config["browse_path"], case.provider)
                        self.assertEqual(device_config["mode"], DeviceConfig.Mode.STANDARD)
                        self.assertEqual(device_config["metadata"]["source"], "sim_device_config")
                        self.assertEqual(
                            [(tag["name"], tag["data_type"]) for tag in device_config["tags"]],
                            expected["tags"],
                        )


def test_real_tag_data_path_discovery_skips_cleanly_when_files_are_absent():
    with TemporaryDirectory() as temp_dir:
        assert discover_real_tag_data_files(Path(temp_dir), provider="Tag_02") is None


@pytest.mark.acceptance
@pytest.mark.django_db
@pytest.mark.skipif(
    os.environ.get(REAL_TAG_DATA_ACCEPTANCE_ENV) != "1",
    reason="set %s=1 to import real tag_data/tag_data files" % REAL_TAG_DATA_ACCEPTANCE_ENV,
)
def test_import_tag_data_catalog_command_smokes_real_tag_02_files_if_present():
    paths = discover_real_tag_data_files(provider="Tag_02")
    if paths is None:
        pytest.skip("real tag_data/tag_data Tag_02 files are not present")
    devices_path, tags_path = paths

    call_command(
        "import_tag_data_catalog",
        "Tag_02_RealSmoke",
        "--devices",
        str(devices_path),
        "--tags",
        str(tags_path),
        "--skip-raw-config",
    )

    assert TagProvider.objects.filter(name="Tag_02_RealSmoke").exists()
    assert DeviceConfig.objects.filter(source_provider__name="Tag_02_RealSmoke").count() > 0
    assert TagConfig.objects.filter(base_tag__provider="Tag_02_RealSmoke").count() > 0



class LiveTagDataIngestTests(TestCase):
    def test_ingest_live_tag_data_catalog_uses_fluxy_export_and_device_list(self):
        fx = fake_fluxy()

        result = ingest_live_tag_data_catalog(fx, source_provider="default", provider_name="Live_01")

        self.assertEqual(result.device_count, 2)
        self.assertEqual(result.tag_count, 3)
        self.assertEqual(fx.tag.export_calls, [("[default]", True)])
        self.assertEqual(fx.device.list_calls, 1)
        self.assertTrue(TagProvider.objects.filter(name="Live_01", source=TagProvider.Source.IGNITION_PROVIDER).exists())
        self.assertEqual(DeviceConfig.objects.get(source_provider__name="Live_01", base_device__name="RTU_01").source_detail, "ServerClient")
        self.assertEqual(TagConfig.objects.get(base_tag__provider="Live_01", source_path="Area/Standalone").device.name, "PLC_01")

    def test_import_live_tag_catalog_command_uses_fluxy_without_live_ignition(self):
        fx = fake_fluxy()
        with patch("fluxy.Fluxy", return_value=fx) as fluxy_class:
            call_command("import_live_tag_catalog", "default", "--provider", "Live_01", "--base-url", "http://gateway/flux", "--token", "secret")

        fluxy_class.assert_called_once_with(base_url="http://gateway/flux", token="secret", tag_provider="default")
        self.assertEqual(TagConfig.objects.filter(base_tag__provider="Live_01").count(), 3)


class catalog_files:
    def __init__(self, *, opc_server=""):
        self.opc_server = opc_server

    def __enter__(self):
        self.temp_dir = TemporaryDirectory()
        base = Path(self.temp_dir.name)
        devices_path = base / "devices.txt"
        tags_path = base / "tags.json"
        devices_path.write_text("RTU_01\tOPC UA\tCONNECTED\tServerClient\nPLC_01\tControlLogix\tConnected\t\n", encoding="utf-8")
        tags_path.write_text(json.dumps(provider_export_fixture(opc_server=self.opc_server)), encoding="utf-8")
        return devices_path, tags_path

    def __exit__(self, exc_type, exc, traceback):
        self.temp_dir.cleanup()


def provider_export_fixture(*, opc_server=""):
    return {
        "name": "",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "RTU_01",
                        "tagType": "UdtInstance",
                        "parameters": {"OPC_Device": "RTU_01"},
                        "tags": [
                            {
                                "name": "PV",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Float4",
                                "opcServer": opc_server,
                                "opcItemPath": "ns=2;s=RTU_01.40001F",
                            },
                            {
                                "name": "Running",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Boolean",
                                "opcServer": opc_server,
                                "opcItemPath": "ns=2;s=RTU_01.00001B",
                            },
                        ],
                    },
                    {
                        "name": "Standalone",
                        "tagType": "AtomicTag",
                        "valueSource": "opc",
                        "dataType": "Int4",
                        "opcServer": opc_server,
                        "opcItemPath": "ns=2;s=PLC_01.Local:1:I.Data.0",
                    },
                ],
            }
        ],
    }


def fake_fluxy():
    return SimpleNamespace(
        tag=FakeLiveTagApi(),
        device=FakeLiveDeviceApi(),
    )


class FakeLiveTagApi:
    def __init__(self):
        self.export_calls = []

    def export_tags(self, tag_path, recursive=True):
        self.export_calls.append((tag_path, recursive))
        return SimpleNamespace(tags=provider_export_fixture(), raw_json=json.dumps(provider_export_fixture()))


class FakeLiveDeviceApi:
    def __init__(self):
        self.list_calls = 0

    def list_devices(self):
        self.list_calls += 1
        return [
            SimpleNamespace(name="RTU_01", driver="OPC UA", state="Connected", enabled=True, payload={"description": "ServerClient"}),
            SimpleNamespace(name="PLC_01", driver="ControlLogix", state="Connected", enabled=True, payload={}),
        ]


class RealTagDataSubset:
    def __init__(self, *, provider, devices, tags, expected):
        self.provider = provider
        self.devices = devices
        self.tags = tags
        self.expected = expected


def discover_real_tag_data_files(root=None, *, provider):
    base = Path(root) if root is not None else project_root_for_real_tag_data()
    tag_data_dir = base / "tag_data" / "tag_data"
    paths_by_provider = {
        "Tag_02": (tag_data_dir / "tag_02 devices.txt", tag_data_dir / "tags02.json"),
        "Tag_05": (tag_data_dir / "tag_05 devices.txt", tag_data_dir / "tag_05.json"),
    }
    paths = paths_by_provider[provider]
    return paths if all(path.exists() for path in paths) else None


def project_root_for_real_tag_data():
    for parent in Path(__file__).resolve().parents:
        if (parent / "tag_data" / "tag_data").is_dir():
            return parent
    return Path(__file__).resolve().parent


class real_tag_data_subset_files:
    def __init__(self, cases):
        self.cases = cases

    def __enter__(self):
        self.temp_dir = TemporaryDirectory()
        base = Path(self.temp_dir.name)
        paths_by_provider = {}
        for case in self.cases:
            provider_dir = base / case.provider
            provider_dir.mkdir()
            devices_path = provider_dir / "devices.txt"
            tags_path = provider_dir / "tags.json"
            devices_path.write_text(case.devices, encoding="utf-8")
            tags_path.write_text(json.dumps(case.tags), encoding="utf-8")
            paths_by_provider[case.provider] = (devices_path, tags_path)
        return paths_by_provider

    def __exit__(self, exc_type, exc, traceback):
        self.temp_dir.cleanup()


def tag_02_subset_provider_export():
    return provider_subset(
        [
            udt_device(
                "WY/BR/PADS/BR05-30/BR05-30_RTU_55",
                "ACM_02",
                [
                    atomic_tag("FlowRate", "Float4", "ns=2;s=ACM_02.FlowRate", opc_server="ACM_02"),
                    atomic_tag("RunStatus", "Boolean", "ns=2;s=ACM_02.RunStatus", opc_server="ACM_02"),
                ],
            ),
            udt_device(
                "WY/BR/PADS/BR05-30/BR05-30_Murphy",
                "BR05_30_Murphy",
                [atomic_tag("Pressure", "Float4", "ns=2;s=BR05_30_Murphy.40001F", opc_server="ACM_02")],
            ),
        ]
    )


def tag_05_subset_provider_export():
    return provider_subset(
        [
            udt_device(
                "Facilities/CGF02/AB_CGF02",
                "AB_CGF02",
                [
                    atomic_tag("Local_Int", "Int4", "ns=2;s=AB_CGF02.Local:1:I.Data.0"),
                    atomic_tag("RunStatus", "Boolean", "ns=2;s=AB_CGF02.RunStatus"),
                ],
            ),
            udt_device(
                "Facilities/CGF04/CGF04_EPOD",
                "CGF04_EPOD",
                [atomic_tag("BusVoltage", "Float4", "ns=2;s=CGF04_EPOD.30001F")],
            ),
        ]
    )


def provider_subset(devices):
    return {
        "name": "",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Acceptance",
                "tagType": "Folder",
                "tags": devices,
            }
        ],
    }


def udt_device(path, opc_device, tags):
    name = path.rsplit("/", 1)[-1]
    return {
        "name": name,
        "tagType": "UdtInstance",
        "parameters": {"OPC_Device": opc_device},
        "tags": tags,
    }


def atomic_tag(name, data_type, opc_item_path, *, opc_server="Ignition OPC UA Server"):
    return {
        "name": name,
        "tagType": "AtomicTag",
        "valueSource": "opc",
        "dataType": data_type,
        "opcServer": opc_server,
        "opcItemPath": opc_item_path,
    }

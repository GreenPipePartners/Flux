from django.test import TestCase

from flux.sim.models import TagNode, TagProvider, TagSelection
from .services import build_provider_tree, import_provider_payload, replace_selection, selected_source_paths


class BaseTagModelTests(TestCase):
    def test_import_provider_payload_persists_tag_tree(self):
        result = import_provider_payload(
            provider_export_fixture(),
            provider_name="simtag",
            source=TagProvider.Source.JSON_UPLOAD,
            source_name="provider.json",
        )

        self.assertEqual(result.provider.name, "simtag")
        self.assertEqual(TagNode.objects.filter(provider=result.provider).count(), 4)
        self.assertTrue(TagNode.objects.filter(provider=result.provider, path="Area/Device01/PV").exists())

    def test_provider_tree_marks_sim_selection(self):
        import_provider_payload(
            provider_export_fixture(),
            provider_name="simtag",
            source=TagProvider.Source.JSON_UPLOAD,
        )
        replace_selection("simtag", ["Area/Device01"])

        tree = build_provider_tree("simtag")

        self.assertIsNotNone(tree)
        self.assertEqual(tree.selected_count, 1)
        self.assertTrue(tree.nodes[0].selected)
        self.assertFalse(tree.nodes[0].partial)
        self.assertTrue(tree.nodes[0].children_list[0].selected)

    def test_selected_source_paths_returns_opc_leaf_paths(self):
        provider = import_provider_payload(
            provider_export_fixture(),
            provider_name="simtag",
            source=TagProvider.Source.JSON_UPLOAD,
        ).provider
        TagSelection.objects.create(provider=provider, path="Area", purpose=TagSelection.Purpose.SIM)

        self.assertEqual(selected_source_paths("simtag"), ["Area/Device01/PV"])


def provider_export_fixture():
    return {
        "name": "simtag",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Device01",
                        "tagType": "UdtInstance",
                        "tags": [
                            {
                                "name": "PV",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Float4",
                                "opcServer": "ACM_02",
                                "opcItemPath": "ns=2;s=Device01.40001F",
                            }
                        ],
                    }
                ],
            }
        ],
    }

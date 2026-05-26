from django.test import TestCase

from .catalog import component_template_specs, ensure_catalog
from .compiler import compile_system
from .fixtures import build_basic_motor_starter_system
from .models import ComponentTemplate
from .models import PotentialSystem
from .models import TerminalPotentialBinding
from .models import ValidationFinding


class SchematicsCatalogTests(TestCase):
    def test_component_template_specs_are_deterministic_and_side_effect_free(self):
        before_count = ComponentTemplate.objects.count()

        specs = {spec.key: spec for spec in component_template_specs()}

        self.assertEqual(ComponentTemplate.objects.count(), before_count)
        starter = specs["starter_3pole_24vdc"]
        self.assertEqual([terminal.key for terminal in starter.terminals], ["L1", "L2", "L3", "T1", "T2", "T3", "A1", "A2"])
        self.assertEqual([role.key for role in starter.roles], ["main_power_contacts", "coil"])
        self.assertEqual(starter.roles[0].potential_system_key, "480VAC_3PH")
        self.assertEqual(starter.roles[1].potential_system_key, "24VDC_CONTROL")
        self.assertEqual(starter.relations[0].condition_key, "coil.energized")

    def test_ensure_catalog_persists_potential_systems_and_relational_templates(self):
        ensure_catalog()

        self.assertEqual(
            list(PotentialSystem.objects.order_by("key").values_list("key", flat=True)),
            ["24VDC_CONTROL", "480VAC_3PH"],
        )
        starter = ComponentTemplate.objects.get(key="starter_3pole_24vdc")
        self.assertEqual(
            list(starter.terminal_templates.order_by("sort_order").values_list("key", flat=True)),
            ["L1", "L2", "L3", "T1", "T2", "T3", "A1", "A2"],
        )
        role_systems = {
            role.key: role.potential_system.key
            for role in starter.role_templates.select_related("potential_system").order_by("key")
        }
        self.assertEqual(role_systems, {"coil": "24VDC_CONTROL", "main_power_contacts": "480VAC_3PH"})
        relation = starter.relation_templates.get(key="coil_energized_closes_main_contacts")
        self.assertEqual(relation.source_role_template.key, "coil")
        self.assertEqual(relation.target_role_template.key, "main_power_contacts")
        self.assertEqual(relation.relation_type, "behavioral")


class SchematicsCompilerTests(TestCase):
    def test_basic_motor_starter_fixture_compiles_conditional_cross_circuit_behavior(self):
        system = build_basic_motor_starter_system()

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.COMPLETE)
        self.assertFalse(ValidationFinding.objects.filter(compile_run=run, severity=ValidationFinding.Severity.ERROR).exists())
        self.assertEqual(system.circuits.count(), 2)
        self.assertEqual(system.sources.count(), 2)
        self.assertEqual(set(system.components.values_list("reference", flat=True)), {"DS1", "PS1", "M1", "MOT1", "PB1"})

        starter_relation = system.components.get(reference="M1").internal_relations.get(
            key="coil_energized_closes_main_contacts"
        )
        self.assertEqual(starter_relation.source_role.key, "coil")
        self.assertEqual(starter_relation.source_role.template.potential_system.key, "24VDC_CONTROL")
        self.assertEqual(starter_relation.target_role.key, "main_power_contacts")
        self.assertEqual(starter_relation.target_role.template.potential_system.key, "480VAC_3PH")
        self.assertEqual(starter_relation.relation_type, "behavioral")

        starter_t1_binding = TerminalPotentialBinding.objects.get(
            compile_run=run,
            terminal__component__reference="M1",
            terminal__key="T1",
            role__key="main_power_contacts",
        )
        self.assertEqual(starter_t1_binding.circuit_potential.key, "L1")
        self.assertEqual(starter_t1_binding.condition_key, "coil.energized")

        coil_a1_binding = TerminalPotentialBinding.objects.get(
            compile_run=run,
            terminal__component__reference="M1",
            terminal__key="A1",
            role__key="coil",
        )
        self.assertEqual(coil_a1_binding.circuit_potential.key, "+24V")
        self.assertEqual(coil_a1_binding.condition_key, "")

    def test_compiler_rejects_role_bound_to_incompatible_potential_system(self):
        system = build_basic_motor_starter_system()
        power_circuit = system.circuits.get(name="480 VAC motor power")
        starter = system.components.get(reference="M1")
        coil_role = starter.roles.get(key="coil")
        power_circuit.participants.create(component=starter, role=coil_role, sort_order=99)

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="role_potential_mismatch",
            ).exists()
        )

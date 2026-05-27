import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .catalog import component_template_specs, ensure_catalog
from .compiler import compile_system
from .fixtures import build_basic_motor_starter_system
from .models import ComponentTemplate
from .models import Connection
from .models import IOPoint
from .models import PotentialSystem
from .models import SourceConnection
from .models import TerminalPotentialBinding
from .models import ValidationFinding
from .projections import compile_run_diagnostic_payload
from .reasoning import explain_component_energization


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
        self.assertEqual(starter.roles[0].continuities[0].condition_key, "coil.energized")
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
        main_contacts = starter.role_templates.get(key="main_power_contacts")
        self.assertEqual(
            list(
                main_contacts.continuity_templates.order_by("sort_order").values_list(
                    "from_terminal_template__key",
                    "to_terminal_template__key",
                    "condition_key",
                )
            ),
            [("L1", "T1", "coil.energized"), ("L2", "T2", "coil.energized"), ("L3", "T3", "coil.energized")],
        )
        self.assertNotIn("continuity_pairs", main_contacts.metadata)
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
        self.assertEqual(system.sources.get(name="Plant 480 VAC 3PH").terminals.count(), 4)
        self.assertEqual(system.sources.get(name="PS1 24 VDC Output").terminals.count(), 3)
        self.assertEqual(set(system.components.values_list("reference", flat=True)), {"DS1", "PS1", "M1", "MOT1", "PB1"})
        self.assertEqual(system.field_instruments.count(), 1)
        self.assertEqual(system.io_points.count(), 4)
        self.assertEqual(system.drives.count(), 1)
        self.assertEqual(run.summary["field_instruments"], 1)
        self.assertEqual(run.summary["io_points"], 4)
        self.assertEqual(run.summary["drives"], 1)

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
            binding_kind="interface",
        )
        self.assertEqual(starter_t1_binding.circuit_potential.key, "L1")
        self.assertEqual(starter_t1_binding.condition_key, "coil.energized")

        coil_a1_binding = TerminalPotentialBinding.objects.get(
            compile_run=run,
            terminal__component__reference="M1",
            terminal__key="A1",
            role__key="coil",
            binding_kind="interface",
        )
        self.assertEqual(coil_a1_binding.circuit_potential.key, "+24V")
        self.assertEqual(coil_a1_binding.condition_key, "")

        coil_a1_net_binding = TerminalPotentialBinding.objects.get(
            compile_run=run,
            terminal__component__reference="M1",
            terminal__key="A1",
            role__key="coil",
            binding_kind="net",
        )
        self.assertEqual(coil_a1_net_binding.circuit_potential.key, "+24V")
        self.assertEqual(coil_a1_net_binding.condition_key, "")
        self.assertEqual(coil_a1_net_binding.metadata["net"], "+24V_after_button")

        motor_t1_net_binding = TerminalPotentialBinding.objects.get(
            compile_run=run,
            terminal__component__reference="MOT1",
            terminal__key="T1",
            role__key="three_phase_load",
            binding_kind="net",
        )
        self.assertEqual(motor_t1_net_binding.circuit_potential.key, "L1")
        self.assertEqual(motor_t1_net_binding.condition_key, "")
        self.assertEqual(motor_t1_net_binding.metadata["net"], "L1_motor")

        main_contact_continuities = system.components.get(reference="M1").roles.get(key="main_power_contacts").continuities.order_by(
            "sort_order"
        )
        self.assertEqual(
            list(main_contact_continuities.values_list("from_terminal__key", "to_terminal__key", "condition_key")),
            [("L1", "T1", "coil.energized"), ("L2", "T2", "coil.energized"), ("L3", "T3", "coil.energized")],
        )

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

    def test_compiler_rejects_continuity_pair_potential_mismatch(self):
        system = build_basic_motor_starter_system()
        starter = system.components.get(reference="M1")
        main_contacts = starter.roles.get(key="main_power_contacts")
        continuity = main_contacts.continuities.get(from_terminal__key="L1", to_terminal__key="T1")
        continuity.to_terminal = starter.terminals.get(key="T2")
        continuity.save(update_fields=["to_terminal"])

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="continuity_potential_mismatch",
            ).exists()
        )

    def test_compiler_rejects_missing_source_connection(self):
        system = build_basic_motor_starter_system()
        power_circuit = system.circuits.get(name="480 VAC motor power")
        power_circuit.source_connections.get(source_terminal__key="L3").delete()

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="missing_source_connection",
            ).exists()
        )

    def test_compiler_rejects_source_connection_potential_mismatch(self):
        system = build_basic_motor_starter_system()
        power_circuit = system.circuits.get(name="480 VAC motor power")
        source_connection = power_circuit.source_connections.get(source_terminal__key="L1")
        source_connection.net = power_circuit.nets.get(key="L2_source")
        source_connection.save(update_fields=["net"])

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="source_connection_potential_mismatch",
            ).exists()
        )

    def test_compiler_rejects_source_terminal_from_wrong_source(self):
        system = build_basic_motor_starter_system()
        power_circuit = system.circuits.get(name="480 VAC motor power")
        control_source = system.sources.get(name="PS1 24 VDC Output")
        SourceConnection.objects.create(
            circuit=power_circuit,
            net=power_circuit.nets.get(key="L1_source"),
            source_terminal=control_source.terminals.get(key="+24V"),
        )

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="source_connection_source_mismatch",
            ).exists()
        )

    def test_compile_run_diagnostic_payload_is_read_only_projection(self):
        system = build_basic_motor_starter_system()
        run = compile_system(system)

        payload = compile_run_diagnostic_payload(run)

        self.assertEqual(payload["system"]["slug"], "basic-480-motor-starter")
        self.assertEqual(payload["compile_run"]["status"], run.Status.COMPLETE)
        self.assertEqual(payload["counts"]["circuits"], 2)
        self.assertEqual(payload["counts"]["components"], 5)
        self.assertEqual(payload["counts"]["field_instruments"], 1)
        self.assertEqual(payload["counts"]["io_points"], 4)
        self.assertEqual(payload["counts"]["drives"], 1)
        control_source = next(source for source in payload["sources"] if source["name"] == "PS1 24 VDC Output")
        self.assertEqual(control_source["terminals"][0]["key"], "+24V")
        self.assertIn("480 VAC motor power", {circuit["name"] for circuit in payload["circuits"]})
        power_circuit = next(circuit for circuit in payload["circuits"] if circuit["name"] == "480 VAC motor power")
        self.assertEqual(power_circuit["source_connections"][0]["source_terminal"], "L1")
        self.assertEqual(power_circuit["source_connections"][0]["net"], "L1_source")
        starter = next(component for component in payload["components"] if component["reference"] == "M1")
        main_contacts = next(role for role in starter["roles"] if role["key"] == "main_power_contacts")
        self.assertEqual(main_contacts["continuities"][0]["condition"], "coil.energized")
        self.assertTrue(
            any(
                binding["component"] == "MOT1"
                and binding["terminal"] == "T1"
                and binding["metadata"].get("net") == "L1_motor"
                for binding in payload["terminal_bindings"]
            )
        )
        instrument = payload["field_instruments"][0]
        self.assertEqual(instrument["reference"], "PT-101")
        self.assertEqual(instrument["process_variable"], "pressure")
        self.assertEqual(instrument["component"], "")
        ai_point = next(io_point for io_point in payload["io_points"] if io_point["reference"] == "AI-101")
        self.assertEqual(ai_point["field_instrument"], "PT-101")
        drive = payload["drives"][0]
        self.assertEqual(drive["reference"], "VFD-201")
        self.assertEqual(drive["drive_kind"], "vfd")
        self.assertEqual([io_point["function"] for io_point in drive["io_points"]], ["run_command", "speed_reference", "running_status"])

    def test_reasoning_traces_motor_power_conditions_through_segmented_nets(self):
        system = build_basic_motor_starter_system()
        compile_system(system)

        explanation = explain_component_energization(system, "MOT1")

        t1_trace = next(
            trace for trace in explanation["terminal_traces"] if trace["terminal"] == "T1" and trace["potential"] == "L1"
        )
        self.assertEqual(t1_trace["conditions"], ["handle.closed", "coil.energized"])
        self.assertTrue(any("L1_source" in step["label"] for step in t1_trace["steps"]))
        self.assertTrue(any("L1_motor" in step["label"] for step in t1_trace["steps"]))

    def test_reasoning_traces_starter_coil_control_conditions(self):
        system = build_basic_motor_starter_system()
        compile_system(system)

        explanation = explain_component_energization(system, "M1")

        a1_trace = next(
            trace for trace in explanation["terminal_traces"] if trace["terminal"] == "A1" and trace["potential"] == "+24V"
        )
        self.assertEqual(a1_trace["conditions"], ["input_power.valid", "button.pressed"])
        self.assertTrue(any(relation["condition"] == "coil.energized" for relation in explanation["component_relations"]))

    def test_motor_starter_report_command_outputs_diagnostic_json(self):
        output = StringIO()

        call_command("schematics_motor_starter_report", "--json", stdout=output)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["system"]["slug"], "basic-480-motor-starter")
        self.assertEqual(payload["compile_run"]["status"], "complete")
        self.assertEqual(
            payload["counts"],
            {"sources": 2, "circuits": 2, "components": 5, "field_instruments": 1, "io_points": 4, "drives": 1},
        )
        self.assertTrue(payload["terminal_bindings"])

    def test_compiler_rejects_io_point_terminal_from_wrong_component(self):
        system = build_basic_motor_starter_system()
        starter = system.components.get(reference="M1")
        motor = system.components.get(reference="MOT1")
        IOPoint.objects.create(
            system=system,
            reference="BAD-IO",
            name="Bad terminal mapping",
            io_kind="digital_input",
            direction=IOPoint.Direction.INPUT,
            signal_kind="discrete_24vdc",
            component=starter,
            terminal=motor.terminals.get(key="T1"),
        )

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="io_point_terminal_component_mismatch",
            ).exists()
        )

    def test_compiler_rejects_missing_required_role_terminal(self):
        system = build_basic_motor_starter_system()
        motor = system.components.get(reference="MOT1")
        motor.roles.get(key="three_phase_load").terminal_links.get(terminal__key="T1").delete()

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="missing_required_role_terminal",
            ).exists()
        )

    def test_compiler_rejects_net_potential_mismatch(self):
        system = build_basic_motor_starter_system()
        power_circuit = system.circuits.get(name="480 VAC motor power")
        motor_t1_connection = power_circuit.connections.get(to_terminal__component__reference="MOT1", to_terminal__key="T1")
        motor_t1_connection.net = power_circuit.nets.get(key="L2_motor")
        motor_t1_connection.save(update_fields=["net"])

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="net_potential_mismatch",
            ).exists()
        )

    def test_compiler_rejects_direct_control_terminal_connection_in_power_circuit(self):
        system = build_basic_motor_starter_system()
        power_circuit = system.circuits.get(name="480 VAC motor power")
        starter = system.components.get(reference="M1")
        Connection.objects.create(
            circuit=power_circuit,
            net=power_circuit.nets.get(key="L1_source"),
            from_terminal=starter.terminals.get(key="L1"),
            to_terminal=starter.terminals.get(key="A1"),
        )

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="terminal_not_in_circuit",
                object_id=starter.terminals.get(key="A1").id,
            ).exists()
        )

    def test_compiler_rejects_source_and_circuit_potential_set_mismatch(self):
        system = build_basic_motor_starter_system()
        power_source = system.sources.get(name="Plant 480 VAC 3PH")
        power_source.terminals.get(key="L3").delete()
        power_source.potentials.get(key="L3").delete()

        run = compile_system(system)

        self.assertEqual(run.status, run.Status.FAILED)
        self.assertTrue(
            ValidationFinding.objects.filter(
                compile_run=run,
                severity=ValidationFinding.Severity.ERROR,
                code="source_potential_set_mismatch",
            ).exists()
        )

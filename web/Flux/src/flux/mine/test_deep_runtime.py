from __future__ import annotations

from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from flux_deep.rll import RllInstruction, RllProgram, RllRung, TagSeed, initial_state_from_tags

from .models import PlcRungFact, PlcTagFact


class MineDeepRuntimeTests(TestCase):
    def test_persisted_hello_world_instruction_model_executes_bounded_pulses(self) -> None:
        call_command("flux_mine_source", str(repo_root() / "logix_samples" / "hello_world.L5X"), stdout=StringIO())

        program = RllProgram(
            tuple(
                RllRung.from_text_and_instructions(
                    rung.text,
                    tuple(
                        RllInstruction.from_row_payload(instruction.mnemonic, instruction.operands, instruction.raw)
                        for instruction in rung.instructions.all()
                    ),
                )
                for rung in PlcRungFact.objects.prefetch_related("instructions").order_by("sort_order")
            )
        )
        state = initial_state_from_tags(
            TagSeed(tag.name, tag.data_type_name, tag.raw)
            for tag in PlcTagFact.objects.filter(scope="MainProgram")
        )

        program.scan(state, scan_ms=100)
        self.assertEqual(state.values["hello_world"], "hello")

        for _ in range(9):
            program.scan(state, scan_ms=100)
        self.assertIs(state.values["world_latch"], True)
        self.assertEqual(state.values["hello_world"], "world")

        for _ in range(9):
            program.scan(state, scan_ms=100)
        self.assertIs(state.values["world_latch"], False)
        self.assertEqual(state.values["hello_world"], "hello")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]

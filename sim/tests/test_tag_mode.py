from datetime import datetime, timedelta, timezone

from flux_sim.tag_mode import TagModeConfig, TagModeKind, value_to_write


def test_write_to_other_tag_response_emits_side_write():
    now = datetime(2026, 5, 19, tzinfo=timezone.utc)

    result = value_to_write(
        1,
        now=now,
        config=TagModeConfig(
            kind=TagModeKind.WRITE_TO_OTHER_TAG_RESPONSE,
            mode_config={"response_tag_path": "[default]Response", "response_value": 10},
        ),
    )

    assert result.value == 1
    assert result.side_writes[0].tag_path == "[default]Response"
    assert result.side_writes[0].value == 10


def test_write_to_other_tag_response_respects_trigger_value():
    now = datetime(2026, 5, 19, tzinfo=timezone.utc)
    config = TagModeConfig(
        kind=TagModeKind.WRITE_TO_OTHER_TAG_RESPONSE,
        mode_config={"response_tag_path": "[default]Response", "response_value": 10, "trigger_value": 1},
    )

    no_match = value_to_write(0, now=now, config=config)
    match = value_to_write(1, now=now + timedelta(seconds=1), config=config)

    assert no_match.side_writes == ()
    assert len(match.side_writes) == 1


def test_write_to_other_tag_response_without_response_tag_path_has_no_side_write():
    now = datetime(2026, 5, 19, tzinfo=timezone.utc)

    result = value_to_write(
        1,
        now=now,
        config=TagModeConfig(kind=TagModeKind.WRITE_TO_OTHER_TAG_RESPONSE, mode_config={"response_value": 10}),
    )

    assert result.value == 1
    assert result.side_writes == ()


def test_write_to_other_tag_response_strips_blank_response_tag_path():
    now = datetime(2026, 5, 19, tzinfo=timezone.utc)

    result = value_to_write(
        1,
        now=now,
        config=TagModeConfig(
            kind=TagModeKind.WRITE_TO_OTHER_TAG_RESPONSE,
            mode_config={"response_tag_path": "   ", "response_value": 10},
        ),
    )

    assert result.value == 1
    assert result.side_writes == ()

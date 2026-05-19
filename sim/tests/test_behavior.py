from datetime import datetime, timedelta, timezone

from flux_sim.behavior import TagBehaviorConfig, TagBehaviorKind, value_to_write


def test_slow_response_initializes_immediately():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    result = value_to_write(
        10,
        now=now,
        config=TagBehaviorConfig(kind=TagBehaviorKind.SLOW_RESPONSE, response_delay_seconds=5),
    )

    assert result.value == 10
    assert result.pending_value is None


def test_slow_response_holds_current_value_until_delay_expires():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    delayed = value_to_write(
        20,
        now=now,
        config=TagBehaviorConfig(
            kind=TagBehaviorKind.SLOW_RESPONSE,
            response_delay_seconds=5,
            last_value=10,
        ),
    )

    assert delayed.value == 10
    assert delayed.pending_value == 20
    assert delayed.pending_apply_at == now + timedelta(seconds=5)

    applied = value_to_write(
        20,
        now=now + timedelta(seconds=5),
        config=TagBehaviorConfig(
            kind=TagBehaviorKind.SLOW_RESPONSE,
            response_delay_seconds=5,
            last_value=10,
            pending_value=20,
            pending_apply_at=now + timedelta(seconds=5),
        ),
    )

    assert applied.value == 20
    assert applied.pending_value is None


def test_ignores_write_keeps_current_value_after_initialization():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)

    initial = value_to_write(
        10,
        now=now,
        config=TagBehaviorConfig(kind=TagBehaviorKind.IGNORES_WRITE),
    )
    ignored = value_to_write(
        20,
        now=now + timedelta(seconds=1),
        config=TagBehaviorConfig(kind=TagBehaviorKind.IGNORES_WRITE, last_value=initial.value),
    )

    assert initial.value == 10
    assert ignored.value == 10

from __future__ import annotations

from datetime import timedelta
import os
from pathlib import Path
from uuid import uuid4

import pytest
from django.utils import timezone

from .engine import configure_enabled_tags, delete_configured_tags, write_due_tags
from .models import SimSchedule, SimTag


@pytest.mark.django_db
def test_tag_mode_application_sequence_writes_modes_and_cleans_up_with_mocks():
    SimTag.objects.update(enabled=False)
    fx = FakeFluxy()
    now = timezone.now()
    folder_path = "FluxTagModeUnit_%s" % uuid4().hex[:8]
    schedule = SimSchedule.objects.create(name="unit-fast", interval_seconds=1)
    slow, ignored, source, response = create_tag_mode_tags(
        folder_path=folder_path,
        schedule=schedule,
        now=now,
        response_tag_path="[default]%s/ResponseTag" % folder_path,
    )

    try:
        configure_enabled_tags(fx)
        write_due_tags(fx, now=now)
        for tag in (slow, ignored, source):
            tag.next_write_at = now + timedelta(seconds=1)
            tag.save(update_fields=["next_write_at"])
        write_due_tags(fx, now=now + timedelta(seconds=1))
    finally:
        delete_configured_tags(fx, provider="default", folder_path=folder_path)

    assert [event[0] for event in fx.events] == ["configure", "write", "write", "delete"]
    assert fx.tag.writes[0] == {
        "tag_paths": [
            "[default]%s/SlowTag" % folder_path,
            "[default]%s/IgnoredTag" % folder_path,
            "[default]%s/SourceTag" % folder_path,
        ],
        "values": [0, 0, 0],
    }
    assert fx.tag.writes[1] == {
        "tag_paths": [
            "[default]%s/SlowTag" % folder_path,
            "[default]%s/IgnoredTag" % folder_path,
            "[default]%s/SourceTag" % folder_path,
            "[default]%s/ResponseTag" % folder_path,
        ],
        "values": [0, 0, 1, 10],
    }
    assert fx.tag.deleted == [["[default]%s" % folder_path]]
    response.refresh_from_db()
    assert response.last_write_at is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("FLUX_LIVE_TAG_MODES") != "1",
    reason="Set FLUX_LIVE_TAG_MODES=1 to run live tag mode integration tests",
)
def test_live_tag_modes_write_and_read_back_through_ignition_memory_tags():
    import fluxy
    from fluxy import FluxyError

    repo_root = Path(__file__).resolve().parents[5]
    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
        project_location=os.getenv(
            "FLUXY_PROJECT_LOCATION",
            str(repo_root / "web" / "ignition_flux_project"),
        ),
    )

    SimTag.objects.update(enabled=False)
    now = timezone.now()
    provider = os.getenv("FLUX_LIVE_TAG_MODES_PROVIDER", "default")
    folder_path = os.getenv("FLUX_LIVE_TAG_MODES_FOLDER", "FluxLiveTagModes_%s" % uuid4().hex[:10])
    schedule = SimSchedule.objects.create(name="live-fast-%s" % uuid4().hex[:8], interval_seconds=1)
    slow, ignored, source, _response = create_tag_mode_tags(
        provider=provider,
        folder_path=folder_path,
        schedule=schedule,
        now=now,
        response_tag_path="[%s]%s/ResponseTag" % (provider, folder_path),
    )

    try:
        configure_enabled_tags(fx)
        write_due_tags(fx, now=now)
        assert_good_value(fx, slow.tag_path, 0)
        assert_good_value(fx, ignored.tag_path, 0)

        for tag in (slow, ignored, source):
            tag.next_write_at = now + timedelta(seconds=1)
            tag.save(update_fields=["next_write_at"])
        write_due_tags(fx, now=now + timedelta(seconds=1))

        assert_good_value(fx, slow.tag_path, 0)
        assert_good_value(fx, ignored.tag_path, 0)
        assert_good_value(fx, source.tag_path, 1)
        assert_good_value(fx, "[%s]%s/ResponseTag" % (provider, folder_path), 10)
    except FluxyError as exc:
        if "Trial Expired" in str(exc):
            pytest.skip("Ignition trial expired during live tag mode integration")
        pytest.fail("live tag mode integration failed: %s" % exc)
    finally:
        try:
            delete_configured_tags(fx, provider=provider, folder_path=folder_path)
        except Exception:
            pass
        SimTag.objects.filter(folder_path=folder_path).delete()


def create_tag_mode_tags(*, folder_path, schedule, now, response_tag_path, provider="default"):
    slow = SimTag.objects.create(
        provider=provider,
        name="SlowTag",
        folder_path=folder_path,
        data_type=SimTag.DataType.INT4,
        pattern=SimTag.Pattern.INT_RAMP,
        behavior=SimTag.Behavior.SLOW_RESPONSE,
        response_delay_seconds=5,
        schedule=schedule,
        next_write_at=now,
    )
    ignored = SimTag.objects.create(
        provider=provider,
        name="IgnoredTag",
        folder_path=folder_path,
        data_type=SimTag.DataType.INT4,
        pattern=SimTag.Pattern.INT_RAMP,
        behavior=SimTag.Behavior.IGNORES_WRITE,
        schedule=schedule,
        next_write_at=now,
    )
    source = SimTag.objects.create(
        provider=provider,
        name="SourceTag",
        folder_path=folder_path,
        data_type=SimTag.DataType.INT4,
        pattern=SimTag.Pattern.INT_RAMP,
        behavior=SimTag.Behavior.WRITE_TO_OTHER_TAG_RESPONSE,
        mode_config={"response_tag_path": response_tag_path, "response_value": 10, "trigger_value": 1},
        schedule=schedule,
        next_write_at=now,
    )
    response = SimTag.objects.create(
        provider=provider,
        name="ResponseTag",
        folder_path=folder_path,
        data_type=SimTag.DataType.INT4,
        pattern=SimTag.Pattern.INT_RAMP,
        schedule=schedule,
        next_write_at=now + timedelta(days=1),
    )
    return slow, ignored, source, response


def assert_good_value(fx, tag_path, expected):
    value = fx.tag.read_blocking(tag_path)
    assert "Good" in value.quality
    assert value.value == expected


class FakeFluxy:
    def __init__(self):
        self.events = []
        self.tag = FakeTagNamespace(self.events)


class FakeTagNamespace:
    def __init__(self, events):
        self.events = events
        self.configured = []
        self.writes = []
        self.deleted = []

    def configure(self, tags, base_path=None, collision_policy="o"):
        self.configured.append({"tags": tags, "base_path": base_path, "collision_policy": collision_policy})
        self.events.append(("configure", base_path))
        return []

    def write_blocking(self, tag_paths, values):
        write = {"tag_paths": list(tag_paths), "values": list(values)}
        self.writes.append(write)
        self.events.append(("write", write))
        return []

    def delete_tags(self, tag_paths):
        self.deleted.append(tag_paths)
        self.events.append(("delete", tag_paths))
        return []

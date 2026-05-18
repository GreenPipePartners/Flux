from django.db import models

from flux.base.runtime import RuntimeTag


class TraceProfile(models.Model):
    key = models.SlugField(max_length=120, unique=True)
    label = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    cache_enabled = models.BooleanField(default=True)
    cache_window_minutes = models.PositiveIntegerField(default=1440)
    sync_interval_seconds = models.PositiveIntegerField(default=60)
    history_provider = models.CharField(max_length=255, default="Core Historian")
    max_query_points = models.PositiveIntegerField(default=500_000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.label


class TraceSignal(models.Model):
    profile = models.ForeignKey(TraceProfile, on_delete=models.CASCADE, related_name="signals")
    tag = models.ForeignKey(RuntimeTag, on_delete=models.CASCADE, related_name="trace_signals")
    label = models.CharField(max_length=255, blank=True)
    unit = models.CharField(max_length=80, blank=True)
    axis_key = models.SlugField(max_length=80, default="process")
    axis_label = models.CharField(max_length=120, blank=True)
    axis_unit = models.CharField(max_length=80, blank=True)
    range_min = models.FloatField(blank=True, null=True)
    range_max = models.FloatField(blank=True, null=True)
    color = models.CharField(max_length=40, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    default_visible = models.BooleanField(default=True)
    cache_enabled = models.BooleanField(default=True)
    source_path = models.CharField(max_length=1200, blank=True)
    history_provider = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "tag"], name="unique_trace_signal_profile_tag")]
        indexes = [
            models.Index(fields=["profile", "cache_enabled", "sort_order"], name="trace_sig_profile_cache_idx"),
            models.Index(fields=["tag"], name="trace_signal_tag_idx"),
        ]
        ordering = ["profile__key", "sort_order", "label", "tag__display_name"]

    @property
    def display_label(self) -> str:
        return self.label or self.tag.display_name

    @property
    def display_unit(self) -> str:
        return self.unit or self.tag.engineering_units

    @property
    def historian_provider(self) -> str:
        return self.history_provider or self.profile.history_provider

    @property
    def historian_path(self) -> str:
        path = (self.source_path or self.tag.path).strip("/")
        return f"histprov:{self.historian_provider}:/sys:gateway:/prov:{self.tag.provider}:/tag:{path}"

    def __str__(self) -> str:
        return f"{self.profile.key}: {self.display_label}"


class TraceCachePoint(models.Model):
    signal = models.ForeignKey(TraceSignal, on_delete=models.CASCADE, related_name="cache_points")
    timestamp = models.DateTimeField()
    value_float = models.FloatField()
    quality_code = models.CharField(max_length=120, default="Good")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["signal", "timestamp"], name="unique_trace_cache_signal_timestamp")]
        indexes = [
            models.Index(fields=["signal", "-timestamp"], name="trace_cache_sig_time_idx"),
            models.Index(fields=["timestamp"], name="trace_cache_timestamp_idx"),
        ]
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.signal_id} @ {self.timestamp}: {self.value_float}"


class TraceCacheCursor(models.Model):
    signal = models.OneToOneField(TraceSignal, on_delete=models.CASCADE, related_name="cache_cursor")
    last_timestamp = models.DateTimeField(blank=True, null=True)
    last_sync_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["signal__profile__key", "signal__sort_order"]

    def __str__(self) -> str:
        return f"{self.signal}: {self.last_timestamp or 'never'}"


class TraceAnnotation(models.Model):
    profile = models.ForeignKey(TraceProfile, on_delete=models.CASCADE, related_name="annotations", blank=True, null=True)
    marker_id = models.PositiveIntegerField(blank=True, null=True)
    marker_time = models.DateTimeField()
    text = models.TextField()
    source = models.CharField(max_length=120, default="flux.trace")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["profile", "-marker_time"], name="trace_annot_profile_time_idx")]
        ordering = ["-marker_time", "-id"]

    def __str__(self) -> str:
        return f"{self.marker_time}: {self.text[:60]}"


class TraceAnnotationTarget(models.Model):
    annotation = models.ForeignKey(TraceAnnotation, on_delete=models.CASCADE, related_name="targets")
    signal = models.ForeignKey(TraceSignal, on_delete=models.CASCADE, related_name="annotation_targets", blank=True, null=True)
    historian_path = models.CharField(max_length=1200)
    ignition_storage_id = models.UUIDField(unique=True)
    quality_code = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["annotation"], name="trace_annotation_target_idx"),
            models.Index(fields=["signal"], name="trace_annotation_signal_idx"),
        ]
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.historian_path}: {self.ignition_storage_id}"

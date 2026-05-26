from django.db import models


class Series(models.Model):
    entity = models.OneToOneField("base.Entity", on_delete=models.PROTECT, related_name="plane_series", blank=True, null=True)
    base_tag = models.OneToOneField("base.Tag", on_delete=models.CASCADE, related_name="plane_series")
    enabled = models.BooleanField(default=True)
    latest_enabled = models.BooleanField(default=True)
    history_enabled = models.BooleanField(default=True)
    sample_interval_ms = models.PositiveIntegerField(default=1000)
    storage_key = models.CharField(max_length=1400)
    retention_policy = models.CharField(max_length=120, default="default")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"plane"."series"'
        indexes = [
            models.Index(fields=["enabled"], name="plane_series_enabled_idx"),
            models.Index(fields=["latest_enabled"], name="plane_series_latest_idx"),
            models.Index(fields=["history_enabled"], name="plane_series_history_idx"),
        ]
        ordering = ["base_tag__provider", "base_tag__tagpath"]

    def __str__(self) -> str:
        return self.storage_key


class Latest(models.Model):
    series = models.OneToOneField(Series, on_delete=models.CASCADE, related_name="latest")
    value = models.JSONField(blank=True, null=True)
    quality_code = models.CharField(max_length=120, default="Unknown")
    value_timestamp = models.DateTimeField(blank=True, null=True)
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"plane"."latest"'
        indexes = [models.Index(fields=["read_at"], name="plane_latest_read_idx")]
        ordering = ["series"]

    def __str__(self) -> str:
        return f"{self.series}: {self.value}"


class Sample(models.Model):
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="samples")
    timestamp = models.DateTimeField()
    value_float = models.FloatField()
    quality_code = models.CharField(max_length=120, default="Good")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"plane"."sample"'
        constraints = [models.UniqueConstraint(fields=["series", "timestamp"], name="unique_plane_sample_series_timestamp")]
        indexes = [
            models.Index(fields=["series", "-timestamp"], name="plane_sample_series_time_idx"),
            models.Index(fields=["timestamp"], name="plane_sample_time_idx"),
        ]
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.series} @ {self.timestamp}: {self.value_float}"


class WindowStat(models.Model):
    class Window(models.TextChoices):
        TODAY = "today", "Today"
        ROLLING_7D = "rolling_7d", "Rolling 7 days"
        ROLLING_30D = "rolling_30d", "Rolling 30 days"

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="window_stats")
    window = models.CharField(max_length=40, choices=Window.choices)
    min_value = models.FloatField(blank=True, null=True)
    max_value = models.FloatField(blank=True, null=True)
    sample_count = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    computed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"plane"."window_stat"'
        constraints = [models.UniqueConstraint(fields=["series", "window"], name="unique_plane_window_stat")]
        indexes = [
            models.Index(fields=["series", "window"], name="plane_window_series_idx"),
            models.Index(fields=["computed_at"], name="plane_window_computed_idx"),
        ]
        ordering = ["series", "window"]

    def __str__(self) -> str:
        return f"{self.series}: {self.window}"

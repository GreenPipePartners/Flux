from django.db import models
from django.utils import timezone


DEFAULT_SCHEDULER_NAME = "default"


class TagSchedule(models.Model):
    name = models.CharField(max_length=80, unique=True)
    interval_seconds = models.PositiveIntegerField(default=30)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["interval_seconds", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.interval_seconds}s)"


class RuntimeTag(models.Model):
    class Category(models.TextChoices):
        PRODUCTION = "production", "Production runtime"
        SIMULATION = "simulation", "Simulation"
        TRACE_STRESS = "trace_stress", "Trace stress"

    provider = models.CharField(max_length=120)
    path = models.CharField(max_length=1000)
    display_name = models.CharField(max_length=255)
    asset_name = models.CharField(max_length=255, blank=True)
    engineering_units = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=40, choices=Category.choices, default=Category.PRODUCTION)
    schedule = models.ForeignKey(TagSchedule, on_delete=models.PROTECT, related_name="tags")
    balancer_code = models.PositiveSmallIntegerField(default=1)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "path"], name="unique_runtime_tag_path")
        ]
        ordering = ["asset_name", "display_name"]

    @property
    def full_path(self) -> str:
        return f"[{self.provider}]{self.path}"

    def __str__(self) -> str:
        return self.display_name


class RuntimeSchedulerConfig(models.Model):
    name = models.CharField(max_length=80, default=DEFAULT_SCHEDULER_NAME, unique=True)
    hot_interval_seconds = models.PositiveSmallIntegerField(default=1)
    warm_interval_seconds = models.PositiveSmallIntegerField(default=10)
    warm_cycles_after_hot = models.PositiveSmallIntegerField(default=1)
    cold_bucket_count = models.PositiveSmallIntegerField(default=60)
    current_balancer_code = models.PositiveSmallIntegerField(default=1)
    balancer_increment = models.PositiveSmallIntegerField(default=1)
    demand_lease_seconds = models.PositiveSmallIntegerField(default=5)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    @classmethod
    def default(cls):
        config, _created = cls.objects.get_or_create(name=DEFAULT_SCHEDULER_NAME)
        return config

    def next_balancer_code(self) -> int:
        bucket_count = max(self.cold_bucket_count, 1)
        increment = max(self.balancer_increment, 1)
        return ((self.current_balancer_code - 1 + increment) % bucket_count) + 1

    def advance_balancer_code(self, *, save: bool = True) -> int:
        self.current_balancer_code = self.next_balancer_code()
        if save:
            self.save(update_fields=["current_balancer_code", "updated_at"])
        return self.current_balancer_code

    def __str__(self) -> str:
        return self.name


class LatestTagValue(models.Model):
    tag = models.OneToOneField(RuntimeTag, on_delete=models.CASCADE, related_name="latest_value")
    value = models.JSONField(blank=True, null=True)
    quality_code = models.CharField(max_length=120, default="Good")
    value_timestamp = models.DateTimeField()
    read_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tag__asset_name", "tag__display_name"]

    def is_stale(self, now=None, stale_after_seconds=120) -> bool:
        now = now or timezone.now()
        return (now - self.read_at).total_seconds() > stale_after_seconds

    def __str__(self) -> str:
        return f"{self.tag}: {self.value}"


class TagSample(models.Model):
    tag = models.ForeignKey(RuntimeTag, on_delete=models.CASCADE, related_name="samples")
    value = models.JSONField(blank=True, null=True)
    quality_code = models.CharField(max_length=120, default="Good")
    value_timestamp = models.DateTimeField()
    read_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["tag", "-read_at"])]
        ordering = ["-read_at"]

    def __str__(self) -> str:
        return f"{self.tag} sample at {self.read_at}"


class DailyTagExtreme(models.Model):
    tag = models.ForeignKey(RuntimeTag, on_delete=models.CASCADE, related_name="daily_extremes")
    date = models.DateField(db_index=True)
    min_value = models.FloatField()
    max_value = models.FloatField()
    sample_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tag", "date"], name="unique_daily_tag_extreme")]
        indexes = [models.Index(fields=["tag", "-date"])]
        ordering = ["-date", "tag__asset_name", "tag__display_name"]

    def __str__(self) -> str:
        return f"{self.tag} extremes for {self.date}"

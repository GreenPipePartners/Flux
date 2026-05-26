"""Flux Spot presentation boundary.

Runtime value storage is exposed through `flux.base.runtime` so Spot remains a read-only
current-state visualization surface.
"""

from django.db import models


class LiveScope(models.Model):
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


class LiveCardDefinition(models.Model):
    scope = models.ForeignKey(LiveScope, on_delete=models.CASCADE, related_name="cards")
    title = models.CharField(max_length=255)
    group = models.CharField(max_length=120, blank=True)
    kind = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope", "sort_order", "title"]
        constraints = [
            models.UniqueConstraint(fields=["scope", "title"], name="unique_live_card_definition_title")
        ]

    def __str__(self) -> str:
        return f"{self.scope.slug}: {self.title}"


class LiveCardPointDefinition(models.Model):
    card = models.ForeignKey(LiveCardDefinition, on_delete=models.CASCADE, related_name="points")
    series = models.ForeignKey("plane.Series", on_delete=models.SET_NULL, related_name="spot_points", blank=True, null=True)
    label = models.CharField(max_length=255)
    full_path = models.CharField(max_length=1124)
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["card", "sort_order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["card", "label"], name="unique_live_card_point_label"),
            models.UniqueConstraint(fields=["card", "full_path"], name="unique_live_card_point_path"),
        ]

    def __str__(self) -> str:
        return f"{self.card}: {self.label}"

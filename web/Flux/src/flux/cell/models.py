from __future__ import annotations

from django.db import models


class Bundle(models.Model):
    key = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_name = models.CharField(max_length=255, blank=True)
    source_sha256 = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"cell"."bundle"'
        ordering = ["key"]

    def __str__(self) -> str:
        return self.name


class Cell(models.Model):
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="cells")
    slug = models.SlugField(max_length=120)
    name = models.CharField(max_length=255)
    group = models.CharField(max_length=120, blank=True)
    kind = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"cell"."cell"'
        constraints = [models.UniqueConstraint(fields=["bundle", "slug"], name="unique_draft_cell_slug_per_bundle")]
        ordering = ["bundle__key", "sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Point(models.Model):
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name="points")
    key = models.SlugField(max_length=120)
    label = models.CharField(max_length=255)
    full_path = models.CharField(max_length=1124)
    role = models.CharField(max_length=80, blank=True)
    engineering_units = models.CharField(max_length=80, blank=True)
    include_live = models.BooleanField(default=True)
    include_trace = models.BooleanField(default=False)
    live_order = models.PositiveIntegerField(default=0)
    trace_order = models.PositiveIntegerField(default=0)
    axis_key = models.SlugField(max_length=80, blank=True)
    range_min = models.FloatField(blank=True, null=True)
    range_max = models.FloatField(blank=True, null=True)
    color = models.CharField(max_length=40, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"cell"."point"'
        constraints = [
            models.UniqueConstraint(fields=["cell", "key"], name="unique_draft_cell_point_key"),
            models.UniqueConstraint(fields=["cell", "full_path"], name="unique_draft_cell_point_path"),
        ]
        indexes = [
            models.Index(fields=["include_live", "enabled"], name="cell_point_live_enabled_idx"),
            models.Index(fields=["include_trace", "enabled"], name="cell_point_trace_enabled_idx"),
            models.Index(fields=["full_path"], name="cell_point_full_path_idx"),
        ]
        ordering = ["cell", "live_order", "trace_order", "label"]

    def __str__(self) -> str:
        return f"{self.cell.name}: {self.label}"


class Relationship(models.Model):
    from_cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name="outgoing_relationships")
    to_cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name="incoming_relationships")
    relationship_type = models.CharField(max_length=80)
    label = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"cell"."relationship"'
        constraints = [
            models.UniqueConstraint(
                fields=["from_cell", "relationship_type", "to_cell"],
                name="unique_draft_cell_relationship",
            )
        ]
        indexes = [models.Index(fields=["relationship_type", "enabled"], name="cell_rel_type_enabled_idx")]
        ordering = ["from_cell", "relationship_type", "sort_order", "to_cell"]

    def __str__(self) -> str:
        return f"{self.from_cell.slug} {self.relationship_type} {self.to_cell.slug}"


class Visual(models.Model):
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name="visuals")
    visual_type = models.CharField(max_length=80)
    source_system = models.CharField(max_length=80, blank=True)
    mine_run = models.ForeignKey("mine.MineRun", on_delete=models.SET_NULL, blank=True, null=True, related_name="cell_visuals")
    screen = models.ForeignKey("mine.HmiScreenFact", on_delete=models.SET_NULL, blank=True, null=True, related_name="cell_visuals")
    component = models.ForeignKey("mine.HmiComponentFact", on_delete=models.SET_NULL, blank=True, null=True, related_name="cell_visuals")
    source_screen_key = models.CharField(max_length=1200, blank=True)
    source_item_key = models.CharField(max_length=1200, blank=True)
    x = models.FloatField(blank=True, null=True)
    y = models.FloatField(blank=True, null=True)
    width = models.FloatField(blank=True, null=True)
    height = models.FloatField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"cell"."visual"'
        indexes = [
            models.Index(fields=["cell", "visual_type"], name="cell_visual_type_idx"),
            models.Index(fields=["mine_run", "source_item_key"], name="cell_visual_source_idx"),
        ]
        ordering = ["cell", "sort_order", "visual_type"]

    def __str__(self) -> str:
        return f"{self.cell.name}: {self.visual_type}"


class Source(models.Model):
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name="sources")
    source_type = models.CharField(max_length=80)
    mine_run = models.ForeignKey("mine.MineRun", on_delete=models.SET_NULL, blank=True, null=True, related_name="cell_sources")
    screen = models.ForeignKey("mine.HmiScreenFact", on_delete=models.SET_NULL, blank=True, null=True, related_name="cell_sources")
    component = models.ForeignKey("mine.HmiComponentFact", on_delete=models.SET_NULL, blank=True, null=True, related_name="cell_sources")
    screen_name = models.CharField(max_length=255, blank=True)
    component_path = models.CharField(max_length=1200, blank=True)
    component_name = models.CharField(max_length=255, blank=True)
    component_type = models.CharField(max_length=120, blank=True)
    bounds = models.JSONField(default=dict, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '"cell"."source"'
        indexes = [
            models.Index(fields=["cell", "source_type"], name="cell_source_type_idx"),
            models.Index(fields=["mine_run", "component_path"], name="cell_source_component_idx"),
        ]
        ordering = ["cell", "source_type", "component_name"]

    def __str__(self) -> str:
        return f"{self.cell.name}: {self.component_name or self.source_type}"


class Comment(models.Model):
    cell = models.ForeignKey(Cell, on_delete=models.CASCADE, related_name="comments")
    author_name = models.CharField(max_length=120, blank=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"cell"."comment"'
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["cell", "-created_at"], name="cell_comment_latest_idx")]

    def __str__(self) -> str:
        return f"{self.cell.name}: {self.body[:40]}"


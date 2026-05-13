from django.db import models


class NavigationDimension(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=120)
    query_key = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.label


class NavigationProfile(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return self.label


class NavigationProfileOrder(models.Model):
    profile = models.ForeignKey(NavigationProfile, on_delete=models.CASCADE, related_name="filter_order")
    dimension = models.ForeignKey(NavigationDimension, on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "position"], name="unique_nav_filter_order")]
        ordering = ["profile__key", "position"]

    def __str__(self) -> str:
        return f"{self.profile}: {self.position} {self.dimension.key}"


class NavigationProfileNavOrder(models.Model):
    profile = models.ForeignKey(NavigationProfile, on_delete=models.CASCADE, related_name="nav_order")
    dimension = models.ForeignKey(NavigationDimension, on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "position"], name="unique_nav_traversal_order")]
        ordering = ["profile__key", "position"]

    def __str__(self) -> str:
        return f"{self.profile}: {self.position} {self.dimension.key}"


class NavigationProfileAction(models.Model):
    class FilterMode(models.TextChoices):
        NONE = "none", "None"
        NORMAL = "normal", "Normal"
        UPSTREAM = "upstream", "Upstream"

    profile = models.ForeignKey(NavigationProfile, on_delete=models.CASCADE, related_name="actions")
    step = models.PositiveSmallIntegerField()
    dimension = models.ForeignKey(NavigationDimension, on_delete=models.CASCADE)
    clear = models.BooleanField(default=False)
    filter_mode = models.CharField(max_length=20, choices=FilterMode.choices, default=FilterMode.NONE)
    define = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "step"], name="unique_nav_profile_action_step")]
        ordering = ["profile__key", "step"]

    def __str__(self) -> str:
        return f"{self.profile}: {self.step} {self.dimension.key}"


class NavigationPlacement(models.Model):
    view_key = models.CharField(max_length=120)
    profile = models.ForeignKey(NavigationProfile, on_delete=models.CASCADE, related_name="placements")
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["view_key", "profile"], name="unique_nav_profile_placement")]
        ordering = ["view_key", "profile__key"]

    def __str__(self) -> str:
        return f"{self.view_key}: {self.profile}"


class NavigationStaticOption(models.Model):
    dimension = models.ForeignKey(NavigationDimension, on_delete=models.CASCADE, related_name="static_options")
    value = models.CharField(max_length=120)
    label = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dimension", "value"], name="unique_nav_static_option")]
        ordering = ["dimension__key", "sort_order", "label"]

    def __str__(self) -> str:
        return f"{self.dimension.key}: {self.label}"

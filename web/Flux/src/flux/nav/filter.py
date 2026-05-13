from __future__ import annotations

from dataclasses import dataclass

from .models import NavigationDimension, NavigationProfile, NavigationProfileAction
from .registry import NavigationOption, run_navigation_query


@dataclass(frozen=True)
class NavigationResult:
    profile: NavigationProfile
    filters: dict[str, str | None]
    options: dict[str, list[NavigationOption]]
    order: list[str]
    nav_order: list[str]
    previous_filters: dict[str, str | None]
    next_filters: dict[str, str | None]


class NavigationFilter:
    def __init__(
        self,
        profile: NavigationProfile,
        current_filters: dict[str, str | None],
        category: str,
        *,
        suppress_define: set[str] | None = None,
    ):
        self.profile = profile
        self.category = category
        self.dimensions = {dimension.key: dimension for dimension in NavigationDimension.objects.filter(enabled=True)}
        self.current_filters = {key: current_filters.get(key) for key in self.dimensions}
        self.actions = list(profile.actions.select_related("dimension").order_by("step"))
        self.current_action_matrix = {action.step: action for action in self.actions}
        self.current_order = list(
            profile.filter_order.select_related("dimension").order_by("position").values_list("dimension__key", flat=True)
        )
        self.current_nav_order = list(
            profile.nav_order.select_related("dimension").order_by("position").values_list("dimension__key", flat=True)
        )
        self.current_options = {key: [] for key in self.dimensions}
        self.updated_filters: dict[str, str | None] = {}
        self.suppress_define = suppress_define or set()

    def resolve(self) -> NavigationResult:
        filters, options = self.update_navigation()
        previous_filters, next_filters = self.next_prev_filters(filters, options)
        return NavigationResult(
            profile=self.profile,
            filters=filters,
            options=options,
            order=self.current_order,
            nav_order=self.current_nav_order,
            previous_filters=previous_filters,
            next_filters=next_filters,
        )

    def update_navigation(self):
        self.updated_filters = self.clear_filter_dict()
        for action in self.current_action_matrix.values():
            self.updated_filters = self.query_and_update_filters(action, self.updated_filters)
        for action in self.current_action_matrix.values():
            if action.filter_mode == NavigationProfileAction.FilterMode.NORMAL:
                self.current_options[action.dimension.key] = self.query_dimension(action.dimension, self.updated_filters)
            elif action.filter_mode == NavigationProfileAction.FilterMode.UPSTREAM:
                self.current_options[action.dimension.key] = self.query_dimension(
                    action.dimension,
                    self.upstream_filters(action.dimension.key, self.updated_filters),
                )
        for key, dimension in self.dimensions.items():
            if not self.current_options[key]:
                self.current_options[key] = self.query_dimension(dimension, self.updated_filters)
        return self.updated_filters, self.current_options

    def clear_filter_dict(self) -> dict[str, str | None]:
        filters = self.current_filters.copy()
        for action in self.current_action_matrix.values():
            if action.clear:
                filters[action.dimension.key] = None
        return filters

    def query_and_update_filters(self, action: NavigationProfileAction, filters: dict[str, str | None]):
        options = self.query_dimension(action.dimension, filters)
        self.current_options[action.dimension.key] = options
        if action.define and action.dimension.key not in self.suppress_define and len(options) == 1:
            filters[action.dimension.key] = options[0].value
        if filters.get(action.dimension.key) and filters[action.dimension.key] not in {option.value for option in options}:
            filters[action.dimension.key] = None
        return filters

    def upstream_filters(self, dimension_key: str, filters: dict[str, str | None]) -> dict[str, str | None]:
        if dimension_key not in self.current_order:
            return filters
        dimension_index = self.current_order.index(dimension_key)
        return {
            key: value if key in self.current_order and self.current_order.index(key) < dimension_index else None
            for key, value in filters.items()
        }

    def next_prev_filters(self, filters: dict[str, str | None], options: dict[str, list[NavigationOption]]):
        if self.category not in self.current_nav_order:
            return filters.copy(), filters.copy()
        return self.adjacent_filters(filters, options, direction=-1), self.adjacent_filters(filters, options, direction=1)

    def adjacent_filters(self, filters: dict[str, str | None], options: dict[str, list[NavigationOption]], *, direction: int):
        category = self.category
        current_options = options.get(category, [])
        if not current_options:
            return filters.copy()
        current_value = filters.get(category)
        values = [option.value for option in current_options]
        try:
            index = values.index(current_value)
        except ValueError:
            index = 0
        next_index = index + direction
        if 0 <= next_index < len(values):
            next_category = category
            next_value = values[next_index]
        else:
            current_nav_index = self.current_nav_order.index(category)
            next_nav_index = current_nav_index + direction
            if not 0 <= next_nav_index < len(self.current_nav_order):
                next_category = category
                next_value = values[-1] if direction < 0 else values[0]
            else:
                next_category = self.current_nav_order[next_nav_index]
                next_options = options.get(next_category, [])
                if not next_options:
                    return filters.copy()
                next_value = next_options[-1].value if direction < 0 else next_options[0].value
        next_filters = filters.copy()
        next_filters[next_category] = next_value
        return next_filters

    def query_dimension(self, dimension: NavigationDimension, filters: dict[str, str | None]) -> list[NavigationOption]:
        return run_navigation_query(dimension, filters)

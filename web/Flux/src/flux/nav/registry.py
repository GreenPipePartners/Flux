from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from django.conf import settings

from .models import NavigationDimension, NavigationStaticOption


@dataclass(frozen=True)
class NavigationOption:
    value: str
    label: str


QueryFunc = Callable[[NavigationDimension, dict[str, str | None]], list[NavigationOption]]


def static_options(dimension: NavigationDimension, filters: dict[str, str | None]) -> list[NavigationOption]:
    return [
        NavigationOption(value=option.value, label=option.label)
        for option in NavigationStaticOption.objects.filter(dimension=dimension, enabled=True)
    ]


QUERY_REGISTRY: dict[str, QueryFunc] = {
    "static.field": static_options,
    "static.route": static_options,
    "static.subroute": static_options,
    "static.site": static_options,
    "static.facility": static_options,
    "static.lease": static_options,
    "static.well": static_options,
    "sqlite.route": lambda dimension, filters: sqlite_options("route", filters),
    "sqlite.subroute": lambda dimension, filters: sqlite_options("subroute", filters),
    "sqlite.site": lambda dimension, filters: sqlite_options("site", filters),
    "sqlite.facility": lambda dimension, filters: sqlite_options("facility", filters),
    "sqlite.lease": lambda dimension, filters: sqlite_options("lease", filters),
    "sqlite.well": lambda dimension, filters: sqlite_options("well", filters),
}


def run_navigation_query(dimension: NavigationDimension, filters: dict[str, str | None]) -> list[NavigationOption]:
    try:
        query = QUERY_REGISTRY[dimension.query_key]
    except KeyError as exc:
        raise ValueError(f"Unknown navigation query key: {dimension.query_key}") from exc
    return query(dimension, filters)


def sqlite_options(category: str, filters: dict[str, str | None]) -> list[NavigationOption]:
    database_path = settings.BASE_DIR / "navigation.db"
    if not database_path.exists():
        return []
    query, params = sqlite_query(category, filters)
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [NavigationOption(value=str(row[0]), label=str(row[1])) for row in rows]


def sqlite_query(category: str, filters: dict[str, str | None]):
    params = {
        "route_id": _int_filter(filters.get("route")),
        "site_id": _int_filter(filters.get("site")),
        "subroute_num": _int_filter(filters.get("subroute")),
        "lease_id": _int_filter(filters.get("lease")),
        "well_id": _int_filter(filters.get("well")),
        "facility_id": _int_filter(filters.get("facility")),
    }
    queries = {
        "route": """
            select distinct routes.id, route_name
            from routes
            join sites on sites.route_id = routes.id
            left join cdps on cdps.site_id = sites.id
            left join wells on wells.site_id = sites.id
            where (:route_id is null or sites.route_id = :route_id)
              and (:site_id is null or sites.id = :site_id)
              and (:subroute_num is null or sites.subroute_num = :subroute_num)
              and (:lease_id is null or wells.lease_id = :lease_id or cdps.lease_id = :lease_id)
              and (:well_id is null or wells.id = :well_id)
            order by route_name
        """,
        "subroute": """
            select distinct subroute_num, subroute_num
            from sites
            join routes on routes.id = sites.route_id
            left join cdps on cdps.site_id = sites.id
            left join facilities on cdps.facility_id = facilities.id
            left join wells on wells.site_id = sites.id
            where (:route_id is null or routes.id = :route_id)
              and (:site_id is null or sites.id = :site_id)
              and (:subroute_num is null or subroute_num = :subroute_num)
              and (:lease_id is null or cdps.lease_id = :lease_id or wells.lease_id = :lease_id)
              and (:facility_id is null or facilities.id = :facility_id)
              and (:well_id is null or wells.id = :well_id)
              and subroute_num is not null
            order by subroute_num
        """,
        "site": """
            select distinct sites.id, site_name
            from sites
            join routes on routes.id = sites.route_id
            left join cdps on cdps.site_id = sites.id
            left join facilities on facilities.id = cdps.facility_id
            left join wells on wells.site_id = sites.id
            where (:route_id is null or routes.id = :route_id)
              and (:site_id is null or sites.id = :site_id)
              and (:subroute_num is null or sites.subroute_num = :subroute_num)
              and (:lease_id is null or cdps.lease_id = :lease_id or wells.lease_id = :lease_id)
              and (:facility_id is null or facilities.id = :facility_id)
              and (:well_id is null or wells.id = :well_id)
            order by site_name
        """,
        "facility": """
            select distinct facilities.id, facility_name
            from facilities
            join cdps on cdps.facility_id = facilities.id
            where (:site_id is null or cdps.site_id = :site_id)
              and (:lease_id is null or cdps.lease_id = :lease_id)
              and (:facility_id is null or facilities.id = :facility_id)
            order by facility_name
        """,
        "lease": """
            select distinct leases.id, lease_name
            from leases
            left join cdps on cdps.lease_id = leases.id
            left join wells on wells.lease_id = leases.id
            left join sites on sites.id = cdps.site_id
            where (:route_id is null or sites.route_id = :route_id)
              and (:site_id is null or cdps.site_id = :site_id)
              and (:subroute_num is null or sites.subroute_num = :subroute_num)
              and (:lease_id is null or cdps.lease_id = :lease_id)
              and (:facility_id is null or cdps.facility_id = :facility_id)
              and (:well_id is null or wells.id = :well_id)
            order by lease_name
        """,
        "well": """
            select distinct wells.id, well_name
            from wells
            left join leases on leases.id = wells.lease_id
            left join sites on sites.id = wells.site_id
            left join routes on sites.route_id = routes.id
            where (:route_id is null or routes.id = :route_id)
              and (:site_id is null or sites.id = :site_id)
              and (:subroute_num is null or sites.subroute_num = :subroute_num)
              and (:lease_id is null or leases.id = :lease_id)
              and (:well_id is null or wells.id = :well_id)
            order by well_name
        """,
    }
    return queries[category], params


def _int_filter(value: str | None) -> int | None:
    if value in (None, "", "0"):
        return None
    try:
        return int(value)
    except ValueError:
        return None

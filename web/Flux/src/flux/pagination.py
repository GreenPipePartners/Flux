from __future__ import annotations

from typing import Any

from django.core.paginator import Page, Paginator


TABLE_PAGE_SIZE = 10


def table_page(request: Any, rows: Any, page_param: str, *, per_page: int = TABLE_PAGE_SIZE) -> Page:
    """Return a server-rendered table page using Flux's default row bound."""

    return Paginator(rows, per_page).get_page(request.GET.get(page_param))

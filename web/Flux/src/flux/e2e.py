from __future__ import annotations

import os
import unittest

from django.apps import apps
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command
from django.db import connections


PRESERVED_APP_LABELS = {"contenttypes", "staticfiles"}


class FluxStaticLiveServerTestCase(StaticLiveServerTestCase):
    playwright_skip_message = "Set FLUX_PLAYWRIGHT=1 to run Playwright tests"

    @classmethod
    def setUpClass(cls):
        if os.getenv("FLUX_PLAYWRIGHT") != "1":
            raise unittest.SkipTest(cls.playwright_skip_message)
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest("Install Playwright to run browser tests") from exc

        super().setUpClass()
        try:
            cls._truncate_postgres_test_tables()
            cls._playwright = sync_playwright().start()
            cls._browser = cls._playwright.chromium.launch(headless=True)
        except Exception:
            cls._stop_playwright()
            super().tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls._stop_playwright()
        finally:
            super().tearDownClass()

    @classmethod
    def _stop_playwright(cls) -> None:
        browser = getattr(cls, "_browser", None)
        playwright = getattr(cls, "_playwright", None)
        if browser is not None:
            browser.close()
            cls._browser = None
        if playwright is not None:
            playwright.stop()
            cls._playwright = None

    def _fixture_teardown(self):
        if self._uses_postgres_databases():
            self._truncate_postgres_test_tables()
        else:
            super()._fixture_teardown()

    @classmethod
    def _uses_postgres_databases(cls) -> bool:
        return all(
            connections[alias].vendor == "postgresql"
            for alias in cls._databases_names(include_mirrors=False)
        )

    @classmethod
    def _truncate_postgres_test_tables(cls) -> None:
        for alias in cls._databases_names(include_mirrors=False):
            connection = connections[alias]
            if connection.vendor != "postgresql":
                call_command("flush", verbosity=0, interactive=False, database=alias)
                continue

            relations = managed_app_relations(connection)
            if not relations:
                continue
            with connection.cursor() as cursor:
                cursor.execute(f"TRUNCATE {', '.join(relations)} RESTART IDENTITY CASCADE")


def managed_app_relations(connection) -> list[str]:
    existing_tables = existing_postgres_tables(connection)
    relations = set()
    for model in apps.get_models(include_auto_created=True):
        if not model._meta.managed or model._meta.proxy:
            continue
        if model._meta.app_label in PRESERVED_APP_LABELS:
            continue
        schema, table = split_db_table(model._meta.db_table)
        if (schema, table) in existing_tables:
            relations.add(quote_relation(schema, table))
    return sorted(relations)


def existing_postgres_tables(connection) -> set[tuple[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT schemaname, tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            """
        )
        return set(cursor.fetchall())


def split_db_table(db_table: str) -> tuple[str, str]:
    value = db_table.strip()
    if "." not in value:
        return "public", unquote_identifier(value)
    schema, table = value.split(".", 1)
    return unquote_identifier(schema), unquote_identifier(table)


def quote_relation(schema: str, table: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def quote_identifier(value: str) -> str:
    return '"%s"' % value.replace('"', '""')


def unquote_identifier(value: str) -> str:
    return value.strip().strip('"')

import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from flux.live.models import LiveCardDefinition, LiveCardPointDefinition, LiveScope
from flux.live.selectors import parse_full_tag_path


class Command(BaseCommand):
    help = "Import Flux Live scope/card/point definitions from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--scope", help="Default scope slug when the CSV omits a scope column.")
        parser.add_argument("--replace", action="store_true", help="Replace existing cards for imported scopes.")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        default_scope = options["scope"]
        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
                rows = list(csv.DictReader(csv_file))
        except OSError as exc:
            raise CommandError(str(exc)) from exc

        if not rows:
            raise CommandError("CSV contains no rows")

        imported = import_live_scope_rows(rows, default_scope=default_scope, replace=options["replace"])
        self.stdout.write(
            self.style.SUCCESS(
                "Imported %(scopes)s live scopes, %(cards)s cards, and %(points)s points"
                % imported
            )
        )


def import_live_scope_rows(rows, *, default_scope=None, replace=False):
    normalized_rows = [expanded for row in rows for expanded in expand_row(row, default_scope=default_scope)]
    scope_slugs = {row["scope"] for row in normalized_rows}
    with transaction.atomic():
        if replace:
            LiveCardDefinition.objects.filter(scope__slug__in=scope_slugs).delete()

        scopes = {}
        cards = {}
        point_count = 0
        for row in normalized_rows:
            scope = scopes.get(row["scope"])
            if scope is None:
                scope, _created = LiveScope.objects.update_or_create(
                    slug=row["scope"],
                    defaults={"name": row["scope_name"] or row["scope"], "description": row["description"]},
                )
                scopes[row["scope"]] = scope

            card_key = (scope.slug, row["card"])
            card = cards.get(card_key)
            if card is None:
                card, _created = LiveCardDefinition.objects.update_or_create(
                    scope=scope,
                    title=row["card"],
                    defaults={
                        "group": row["group"],
                        "kind": row["kind"],
                        "sort_order": row["card_order"],
                    },
                )
                cards[card_key] = card

            LiveCardPointDefinition.objects.update_or_create(
                card=card,
                label=row["point"],
                defaults={"full_path": row["full_path"], "sort_order": row["point_order"]},
            )
            point_count += 1

    return {"scopes": len(scopes), "cards": len(cards), "points": point_count}


def expand_row(row, *, default_scope=None):
    normalized = normalize_keys(row)
    if value_from(normalized, "full_path", "tag", "tag_path", "canonical_tag"):
        return [normalize_row(normalized, default_scope=default_scope)]
    tag_columns = sorted(
        (name for name in normalized if name.startswith("tag_") and value_from(normalized, name)),
        key=tag_column_sort_key,
    )
    if not tag_columns:
        return [normalize_row(normalized, default_scope=default_scope)]
    rows = []
    for index, tag_column in enumerate(tag_columns, start=1):
        expanded = dict(normalized)
        expanded["full_path"] = normalized[tag_column]
        expanded["point"] = value_from(normalized, f"{tag_column}_label") or label_from_full_path(normalized[tag_column])
        expanded["point_order"] = str(index)
        rows.append(normalize_row(expanded, default_scope=default_scope))
    return rows


def normalize_row(row, *, default_scope=None):
    scope = value_from(row, "scope", "scope_slug", "live_scope") or default_scope
    card = value_from(row, "card", "card_title", "title", "name")
    kind = value_from(row, "kind")
    point = value_from(row, "point", "point_label", "label")
    full_path = value_from(row, "full_path", "tag", "tag_path", "canonical_tag")
    required = {"scope": scope, "card": card, "kind": kind, "point": point, "full_path": full_path}
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise CommandError("CSV row missing required values: %s" % ", ".join(missing))
    try:
        parse_full_tag_path(full_path)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    return {
        "scope": scope,
        "scope_name": value_from(row, "scope_name", "name"),
        "description": value_from(row, "description"),
        "card": card,
        "group": value_from(row, "group"),
        "kind": kind,
        "card_order": int(value_from(row, "card_order", "card_sort_order", "display_order", "display_order_optional") or 0),
        "point": point,
        "full_path": full_path,
        "point_order": int(value_from(row, "point_order", "point_sort_order") or 0),
    }


def value_from(row, *names):
    for name in names:
        value = row.get(name)
        if value is not None and value.strip():
            return value.strip()
    return ""


def normalize_keys(row):
    return {normalize_key(key): value for key, value in row.items()}


def normalize_key(value):
    cleaned = (
        value.strip()
        .lower()
        .replace("{", "")
        .replace("}", "")
        .replace("(", "")
        .replace(")", "")
    )
    return "_".join(cleaned.split())


def tag_column_sort_key(name):
    suffix = name.removeprefix("tag_")
    return int(suffix) if suffix.isdigit() else 9999


def label_from_full_path(full_path):
    path = full_path.split("]", 1)[-1]
    return path.rsplit("/", 1)[-1].replace("_", " ").title()

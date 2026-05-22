from django.test import TestCase

from .filter import NavigationFilter
from .models import NavigationDimension, NavigationProfile
from .registry import run_navigation_query


class NavigationFilterTests(TestCase):
    def test_seeded_well_profile_preserves_order_structures(self):
        profile = NavigationProfile.objects.get(key="well")
        result = NavigationFilter(profile, {"route": "4"}, "well").resolve()

        self.assertEqual(result.order, ["route", "subroute", "site", "well"])
        self.assertEqual(result.nav_order, ["subroute", "site", "well"])
        self.assertIn("well", result.options)

    def test_nav_index_is_not_public_route(self):
        self.assertEqual(self.client.get("/nav/?profile=well").status_code, 404)

    def test_sqlite_navigation_query_reads_reference_database(self):
        dimension = NavigationDimension.objects.get(key="route")
        dimension.query_key = "sqlite.route"

        options = run_navigation_query(dimension, {})

        self.assertGreaterEqual(len(options), 4)
        self.assertIn("PD-4S", {option.label for option in options})

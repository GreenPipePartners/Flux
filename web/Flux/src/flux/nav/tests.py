import re

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

    def test_nav_index_loads_seeded_panel(self):
        response = self.client.get("/nav/?profile=well")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Well Navigation")
        self.assertContains(response, "nav-options-well")
        self.assertContains(response, 'autocomplete="off"')
        self.assertContains(response, 'spellcheck="false"')
        self.assertNotContains(response, '<select name="profile"')

    def test_changed_field_drives_active_indicator_and_profile(self):
        response = self.client.get("/nav/?profile=well&changed=site&site=AL01-05")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'profile=well')
        self.assertContains(response, 'action=site')
        self.assertContains(response, 'nav-active-indicator is-active')

    def test_changed_field_does_not_hide_display_profile_dropdowns(self):
        response = self.client.get("/nav/?profile=well&changed=site&site=AL01-05")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nav-options-route")
        self.assertContains(response, "nav-options-subroute")
        self.assertContains(response, "nav-options-site")
        self.assertContains(response, "nav-options-well")

    def test_nav_panel_accepts_datalist_value_prefix(self):
        response = self.client.get("/nav/?profile=well&changed=route&route=4:%20PD-4S")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PD-4S")

    def test_nav_panel_resolves_datalist_label_to_value(self):
        response = self.client.get("/nav/?profile=well&changed=route&route=PD-4S")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="PD-4S"')

    def test_well_profile_preserves_selected_site_label(self):
        response = self.client.get("/nav/?profile=well&changed=site&site=AL01-05")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="AL01-05"')

    def test_dropdown_clear_sentinel_still_clears_selected_value(self):
        response = self.client.get("/nav/?profile=well&changed=route&route=--%20clear%20--")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        route_input = re.search(r'<input\s+[^>]*name="route"[^>]*>', content, re.S).group(0)
        self.assertNotIn('<option value="-- clear --">', content)
        self.assertIn('value=""', route_input)

    def test_clear_all_button_preserves_profile_and_clears_filters(self):
        response = self.client.get("/nav/?profile=well")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        route_input = re.search(r'<input\s+[^>]*name="route"[^>]*>', content, re.S).group(0)
        self.assertContains(response, "Clear All")
        self.assertContains(response, 'hx-get="/nav/?profile=well"')
        self.assertIn('value=""', route_input)

    def test_field_clear_button_renders_next_to_label(self):
        response = self.client.get("/nav/?profile=well&changed=route&route=PD-4S")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clear Route")
        self.assertContains(response, 'name="clear"')
        self.assertContains(response, 'value="route"')

    def test_field_clear_button_request_overrides_included_form_value(self):
        response = self.client.get("/nav/?profile=well&changed=route&clear=route&route=PD-4S")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        route_input = re.search(r'<input\s+[^>]*name="route"[^>]*>', content, re.S).group(0)
        self.assertIn('value=""', route_input)

    def test_dropdown_clear_suppresses_auto_define(self):
        response = self.client.get("/nav/?profile=well&changed=site&route=PD-4S&subroute=1&site=--%20clear%20--")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        site_input = re.search(r'<input\s+[^>]*name="site"[^>]*>', content, re.S).group(0)
        self.assertIn('value=""', site_input)

    def test_sqlite_navigation_query_reads_reference_database(self):
        dimension = NavigationDimension.objects.get(key="route")
        dimension.query_key = "sqlite.route"

        options = run_navigation_query(dimension, {})

        self.assertGreaterEqual(len(options), 4)
        self.assertIn("PD-4S", {option.label for option in options})

from django.test import TestCase


class LiveSmokeTests(TestCase):
    def test_live_index_loads(self):
        response = self.client.get("/live/")
        self.assertEqual(response.status_code, 200)

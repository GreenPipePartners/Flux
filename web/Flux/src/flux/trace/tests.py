from django.test import TestCase


class TraceSmokeTests(TestCase):
    def test_trace_index_loads(self):
        response = self.client.get("/trace/")
        self.assertEqual(response.status_code, 200)

from django.core.management import call_command
from django.test import TestCase

from .models import ServeHeartbeat


class ServeSmokeTests(TestCase):
    def test_serve_index_loads(self):
        response = self.client.get("/serve/")

        self.assertEqual(response.status_code, 200)

    def test_flux_worker_once_records_heartbeat(self):
        call_command("flux_worker", "--once", "--service-name", "test-worker")

        self.assertTrue(ServeHeartbeat.objects.filter(service_name="test-worker").exists())

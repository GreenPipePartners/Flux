from django.core.management import call_command
from django.test import TestCase


class OptSmokeTests(TestCase):
    def test_opt_index_loads(self):
        response = self.client.get("/opt/")

        self.assertEqual(response.status_code, 200)

    def test_run_optimizer_command_is_available(self):
        call_command("run_optimizer")

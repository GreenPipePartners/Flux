from django.core.management.base import BaseCommand

from flux.opt.models import RefreshLane


class Command(BaseCommand):
    help = "Run one Flux optimization pass. The adaptive scheduler will be implemented here."

    def handle(self, *args, **options):
        lane_count = RefreshLane.objects.filter(enabled=True).count()
        self.stdout.write("Flux optimizer scaffold ready: %s enabled lanes" % lane_count)

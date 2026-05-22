from django.shortcuts import render

from flux.links import flux_link


def index(request):
    backend_candidates = [
        "Ignition Core Historian / embedded QuestDB",
        "Direct QuestDB",
        "TimescaleDB",
    ]
    return render(
        request,
        "time/index.html",
        {
            "backend_candidates": backend_candidates,
            "purpose_link": flux_link(
                title="Flux Time Purpose",
                description="Flux Time is the planned boundary for historian strategy, sample contracts, and high-volume time-series backend selection.",
                rows=[("Status", "Placeholder"), ("Candidate count", len(backend_candidates))],
                payload={"type": "flux.time.purpose.context", "backend_candidates": backend_candidates},
                docs_path="apps/",
                page_url=request.build_absolute_uri(),
            ),
        },
    )

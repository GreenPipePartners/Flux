from django.shortcuts import render


def index(request):
    return render(
        request,
        "time/index.html",
        {
            "backend_candidates": [
                "Ignition Core Historian / embedded QuestDB",
                "Direct QuestDB",
                "TimescaleDB",
            ],
        },
    )

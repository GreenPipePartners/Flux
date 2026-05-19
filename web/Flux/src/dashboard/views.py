from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect, render

from flux.base.runtime import RuntimeTag

from .forms import InitialSuperuserForm
from .services import (
    bridge_config,
    dashboard_readiness,
    dashboard_runtime_state,
    excluded_interface_runtime_tag_count,
    field_device_status,
    interface_runtime_tags,
    refresh_runtime_tags,
    test_bridge,
    update_bridge_config,
)


def setup_required() -> bool:
    return not get_user_model().objects.exists()


def home(request):
    if setup_required():
        return redirect("dashboard:setup")

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save_bridge":
            base_url = request.POST.get("fluxy_base_url", "").strip()
            token = request.POST.get("fluxy_token", "")
            clear_token = request.POST.get("clear_fluxy_token") == "on"
            if base_url:
                update_bridge_config(base_url=base_url, token=token if token else None, clear_token=clear_token)
                messages.success(request, "Saved Live Ignition Bridge configuration.")
            else:
                messages.warning(request, "Live Ignition Bridge URL is required.")
            return redirect("dashboard:home")
        if action == "test_bridge":
            config = test_bridge()
            if config.last_test_ok:
                messages.success(request, config.last_test_message)
            else:
                messages.error(request, f"Live Ignition Bridge test failed: {config.last_test_message}")
            return redirect("dashboard:home")
        if action == "refresh_stale":
            stale_ids = [int(value) for value in request.POST.getlist("stale_tag_id") if value.isdigit()]
            stale_tags = list(RuntimeTag.objects.filter(id__in=stale_ids, enabled=True).select_related("schedule"))
            try:
                refreshed = refresh_runtime_tags(stale_tags)
            except Exception as exc:
                messages.error(request, f"Stale tag refresh failed: {exc}")
            else:
                messages.success(request, f"Refreshed {refreshed} stale runtime tags from Ignition.")
            return redirect("dashboard:home")

    tags = interface_runtime_tags()
    runtime_state = dashboard_runtime_state(tags)
    readiness = dashboard_readiness(runtime_state)
    service_state = "ok" if all(item.state == "ok" for item in readiness) else "warning"
    bridge = bridge_config()
    device_status = field_device_status()

    return render(
        request,
        "dashboard/home.html",
        {
            "tags": tags,
            "online_count": runtime_state["online_count"],
            "stale_count": runtime_state["stale_count"],
            "bad_quality_count": runtime_state["bad_quality_count"],
            "stale_after_seconds": runtime_state["stale_after_seconds"],
            "tag_count": runtime_state["tag_count"],
            "last_read_at": runtime_state["last_read_at"],
            "excluded_runtime_tag_count": excluded_interface_runtime_tag_count(),
            "readiness": readiness,
            "service_state": service_state,
            "stale_tag_items": runtime_state["stale_tag_items"][:12],
            "stale_tag_overflow": max(runtime_state["stale_count"] - 12, 0),
            "device_status": device_status,
            "bridge": {
                "base_url": bridge.base_url,
                "token_set": bool(bridge.token),
                "online": bridge.last_test_ok,
                "message": bridge.last_test_message,
                "last_test_at": bridge.last_test_at,
            },
        },
    )


def setup(request):
    if not setup_required():
        return redirect("dashboard:home")

    if request.method == "POST":
        form = InitialSuperuserForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Initial Flux superuser created.")
            return redirect("admin:index")
    else:
        form = InitialSuperuserForm()

    return render(request, "dashboard/setup.html", {"form": form})

AUTH_TOKEN = "fluxy-auth-integration-token"  # Optional bearer token. Leave blank to disable auth.
LOGGER_NAME = "Fluxy.WebDev"


def _logger(operation):
    return system.util.getLogger("%s.%s" % (LOGGER_NAME, operation))


def _log_start(operation):
    _logger(operation).info("start")


def _log_success(operation):
    _logger(operation).info("success")


def _log_error(operation, message, exc):
    _logger(operation).error("%s: %s" % (message, exc))


def _unauthorized():
    return {"json": {"ok": False, "error": "Unauthorized"}, "status": 401}


def _bad_request(message, details=None):
    payload = {"ok": False, "error": message}
    if details is not None:
        payload["details"] = details
    return {"json": payload, "status": 400}


def _auth_ok(request):
    if not AUTH_TOKEN:
        return True
    headers = request.get("headers", {}) or {}
    authorization = headers.get("Authorization") or headers.get("authorization") or ""
    return authorization == "Bearer %s" % AUTH_TOKEN


def _json_body(request):
    for key in ["data", "body", "postData", "payload"]:
        data = request.get(key)
        if data is None:
            continue
        if isinstance(data, dict):
            return data
        if hasattr(data, "tostring"):
            data = data.tostring()
        elif hasattr(data, "decode"):
            data = data.decode("utf-8")
        data = str(data).strip()
        if data:
            return system.util.jsonDecode(data)
    return {}


def _request_debug(request):
    details = {"keys": list(request.keys())}
    for key in ["data", "body", "postData", "payload", "params"]:
        if key in request:
            value = request.get(key)
            details[key] = str(type(value))
    return details


def _is_ignition_83_or_newer():
    version = system.util.getVersion()
    major = getattr(version, "major", None)
    minor = getattr(version, "minor", None)
    try:
        return int(major) > 8 or (int(major) == 8 and int(minor) >= 3)
    except Exception:
        parts = str(version).split(".")
        if len(parts) < 2:
            return False
        return int(parts[0]) > 8 or (int(parts[0]) == 8 and int(parts[1]) >= 3)


def _historical_tag_parts(path):
    if not isinstance(path, basestring) or not path.startswith("histprov:"):
        raise ValueError("8.1 historian fallback requires a historical path starting with histprov:")
    provider_end = path.find(":/")
    if provider_end < 0:
        raise ValueError("Historical path is missing provider separator: %s" % path)
    history_provider = path[len("histprov:"):provider_end]
    tag_marker = ":/tag:"
    tag_index = path.find(tag_marker)
    if tag_index < 0:
        raise ValueError("Historical path is missing /tag: section: %s" % path)
    tag_path = path[tag_index + len(tag_marker):]
    provider_marker = ":/prov:"
    provider_index = path.find(provider_marker)
    if provider_index >= 0 and provider_index < tag_index:
        tag_provider = path[provider_index + len(provider_marker):tag_index]
        return history_provider, tag_provider, tag_path
    driver_marker = ":/drv:"
    driver_index = path.find(driver_marker)
    if driver_index >= 0 and driver_index < tag_index:
        driver = path[driver_index + len(driver_marker):tag_index]
        if ":" in driver:
            return history_provider, driver.split(":", 1)[1], tag_path
    raise ValueError("Historical path is missing /prov: or /drv: provider section: %s" % path)


def _store_tag_history_81(paths, values, timestamps, qualities):
    grouped = {}
    for index, path in enumerate(paths):
        history_provider, tag_provider, tag_path = _historical_tag_parts(path)
        key = (history_provider, tag_provider)
        if key not in grouped:
            grouped[key] = {"paths": [], "values": [], "qualities": [], "timestamps": []}
        grouped[key]["paths"].append(tag_path)
        grouped[key]["values"].append(values[index])
        grouped[key]["qualities"].append(qualities[index])
        grouped[key]["timestamps"].append(timestamps[index])
    for key, group in grouped.items():
        system.tag.storeTagHistory(
            key[0],
            key[1],
            group["paths"],
            group["values"],
            group["qualities"],
            _dates_from_millis(group["timestamps"]),
        )


def _quality_list_to_wire(value):
    try:
        return [str(quality) for quality in value]
    except Exception:
        return [str(value)]


def _optional_to_wire(value):
    if value is None:
        return None
    try:
        if value.isPresent():
            return str(value.get())
        return None
    except Exception:
        return str(value)


def _annotation_to_wire(annotation):
    value = annotation.value()
    return {
        "storageId": str(annotation.identifier()),
        "path": str(annotation.source()),
        "startTime": str(annotation.startTime()),
        "endTime": _optional_to_wire(annotation.endTime()),
        "type": str(value.type()),
        "data": str(value.notes()),
        "author": str(value.author()),
    }


def _property_set_to_wire(properties):
    out = {}
    for prop in properties.getProperties():
        name = str(prop.getName())
        value = properties.get(prop)
        if value is not None and not isinstance(value, (basestring, int, long, float, bool)):
            value = str(value)
        out[name] = value
    return out


def _metadata_to_wire(metadata):
    return {
        "path": str(metadata.source()),
        "timestamp": str(metadata.timestamp()),
        "quality": str(metadata.quality()),
        "properties": _property_set_to_wire(metadata.value()),
    }



def _dates_or_none_from_millis(values):
    if values is None:
        return None
    return [system.date.fromMillis(long(value)) for value in values]

operation = "Historian.storeAnnotations"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    paths = payload.get("paths")
    start_times = payload.get("startTimes") or payload.get("start_times")
    end_times = payload.get("endTimes") or payload.get("end_times")
    types = payload.get("types")
    data = payload.get("data")
    storage_ids = payload.get("storageIds") or payload.get("storage_ids")
    deleted = payload.get("deleted")
    if not isinstance(paths, list):
        return _bad_request("Request must include paths list", _request_debug(request))
    if not isinstance(start_times, list):
        return _bad_request("Request must include startTimes list", _request_debug(request))
    start_dates = _dates_or_none_from_millis(start_times)
    end_dates = _dates_or_none_from_millis(end_times)
    if _is_ignition_83_or_newer():
        if deleted is not None:
            qualities = system.historian.storeAnnotations(paths, start_dates, end_dates, types, data, storage_ids, deleted)
        elif storage_ids is not None:
            qualities = system.historian.storeAnnotations(paths, start_dates, end_dates, types, data, storage_ids)
        elif data is not None:
            qualities = system.historian.storeAnnotations(paths, start_dates, end_dates, types, data)
        elif types is not None:
            qualities = system.historian.storeAnnotations(paths, start_dates, end_dates, types)
        elif end_times is not None:
            qualities = system.historian.storeAnnotations(paths, start_dates, end_dates)
        else:
            qualities = system.historian.storeAnnotations(paths, start_dates)
    else:
        if deleted is not None:
            qualities = system.tag.storeAnnotations(paths, start_dates, end_dates, types, data, storage_ids, deleted)
        elif storage_ids is not None:
            qualities = system.tag.storeAnnotations(paths, start_dates, end_dates, types, data, storage_ids)
        elif data is not None:
            qualities = system.tag.storeAnnotations(paths, start_dates, end_dates, types, data)
        elif types is not None:
            qualities = system.tag.storeAnnotations(paths, start_dates, end_dates, types)
        elif end_times is not None:
            qualities = system.tag.storeAnnotations(paths, start_dates, end_dates)
        else:
            qualities = system.tag.storeAnnotations(paths, start_dates)
    _log_success(operation)
    return {"json": {"ok": True, "qualities": _quality_list_to_wire(qualities)}}
except Exception, exc:
    _log_error(operation, "storeAnnotations failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

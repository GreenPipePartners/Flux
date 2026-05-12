AUTH_TOKEN = ""  # Optional bearer token. Leave blank to disable auth.
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


def _dataset_to_wire(dataset):
    rows = []
    column_names = list(dataset.getColumnNames())
    for row_index in range(dataset.getRowCount()):
        row = []
        for column_name in column_names:
            value = dataset.getValueAt(row_index, column_name)
            if hasattr(value, "getTime"):
                value = value.getTime()
            row.append(value)
        rows.append(row)
    return {"rows": rows, "columns": column_names}



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

operation = "Historian.queryRawPoints"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    paths = payload.get("paths")
    start_time = payload.get("startTime") or payload.get("start_time")
    end_time = payload.get("endTime") or payload.get("end_time")
    return_size = int(payload.get("returnSize") or payload.get("return_size") or 100)
    if not isinstance(paths, list):
        return _bad_request("Request must include paths list", _request_debug(request))
    if start_time is None or end_time is None:
        return _bad_request("Request must include startTime and endTime", _request_debug(request))
    column_names = ["value_%d" % index for index in range(len(paths))]
    if _is_ignition_83_or_newer():
        dataset = system.historian.queryRawPoints(
            paths,
            system.date.fromMillis(long(start_time)),
            system.date.fromMillis(long(end_time)),
            column_names,
            "TALL",
            return_size,
            False,
        )
    else:
        dataset = system.tag.queryTagHistory(
            paths=paths,
            startDate=system.date.fromMillis(long(start_time)),
            endDate=system.date.fromMillis(long(end_time)),
            returnSize=return_size,
            aggregationMode="LastValue",
            returnFormat="Tall",
            columnNames=column_names,
            includeBoundingValues=False,
            noInterpolation=True,
        )
    _log_success(operation)
    return {"json": {"ok": True, "result": _dataset_to_wire(dataset), "resultSource": "ignition.dataset", "resultMessage": "Ignition Dataset serialized as columns/rows; Fluxy converted to row mappings"}}
except Exception, exc:
    _log_error(operation, "queryRawPoints failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

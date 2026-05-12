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


def _dataset_rows(dataset):
    rows = []
    column_names = list(dataset.getColumnNames())
    for row_index in range(dataset.getRowCount()):
        item = {}
        for column_name in column_names:
            value = dataset.getValueAt(row_index, column_name)
            if value is not None:
                item[str(column_name)] = value if isinstance(value, bool) else str(value)
        if "name" not in item and "Name" in item:
            item["name"] = item["Name"]
        if "enabled" not in item and "Enabled" in item:
            item["enabled"] = bool(item["Enabled"])
        if "state" not in item and "State" in item:
            item["state"] = item["State"]
        if "driver" not in item and "Driver" in item:
            item["driver"] = item["Driver"]
        rows.append(item)
    return rows

operation = "Device.listDevices"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    devices = _dataset_rows(system.device.listDevices())
    _log_success(operation)
    return {"json": {"ok": True, "devices": devices}}
except Exception, exc:
    _log_error(operation, "listDevices failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

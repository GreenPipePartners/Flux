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


def _read_value(item, key):
    try:
        return item[key]
    except Exception:
        pass
    try:
        return getattr(item, key)
    except Exception:
        pass
    return None


def _connection_info_to_dict(info):
    if hasattr(info, "getColumnNames") and hasattr(info, "getRowCount"):
        column_names = list(info.getColumnNames())
        if info.getRowCount() > 0:
            item = {}
            for column_name in column_names:
                value = info.getValueAt(0, column_name)
                if value is not None:
                    item[str(column_name)] = value if isinstance(value, bool) else str(value)
            return item
    if hasattr(info, "getUnderlyingDataset"):
        return _connection_info_to_dict(info.getUnderlyingDataset())
    try:
        if len(info) > 0:
            return _connection_info_to_dict(info[0])
    except Exception:
        pass
    item = {}
    for key in [
        "Name",
        "name",
        "Status",
        "status",
        "Driver",
        "driver",
        "ConnectURL",
        "connectURL",
        "connectUrl",
        "URL",
        "url",
        "Username",
        "username",
        "ValidationQuery",
        "validationQuery",
        "Enabled",
        "enabled",
    ]:
        value = _read_value(info, key)
        if value is not None:
            item[key] = value if isinstance(value, bool) else str(value)
    if "name" not in item and "Name" in item:
        item["name"] = item["Name"]
    if "status" not in item and "Status" in item:
        item["status"] = item["Status"]
    if not item:
        item["raw"] = str(info)
    return item

operation = "Db.getConnectionInfo"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    name = payload.get("name")
    if not isinstance(name, basestring):
        return _bad_request("Request must include name string", _request_debug(request))
    info = _connection_info_to_dict(system.db.getConnectionInfo(name))
    _log_success(operation)
    return {"json": {"ok": True, "info": info}}
except Exception, exc:
    _log_error(operation, "getConnectionInfo failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

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


def _value_to_wire(value):
    if value is None or isinstance(value, (basestring, int, long, float, bool)):
        return value
    if hasattr(value, "getTime"):
        return value.getTime()
    try:
        return _value_to_wire(value.toDict())
    except Exception:
        pass
    if isinstance(value, dict):
        return dict((str(key), _value_to_wire(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [_value_to_wire(item) for item in value]
    try:
        return system.util.jsonDecode(system.util.jsonEncode(value))
    except Exception:
        return str(value)

operation = "Tag.readBlocking"
DEFAULT_TIMEOUT_MS = 45000
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    tag_paths = payload.get("tagPaths") or payload.get("tag_paths") or payload.get("tag_list")
    timeout_ms = int(payload.get("timeoutMs") or payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
    if not isinstance(tag_paths, list):
        return _bad_request("Request must include tagPaths list", _request_debug(request))
    qualified_values = system.tag.readBlocking(tag_paths, timeout_ms)
    values = []
    for index in range(len(tag_paths)):
        qualified_value = qualified_values[index]
        values.append({
            "tagPath": tag_paths[index],
            "value": _value_to_wire(qualified_value.value),
            "quality": str(qualified_value.quality),
            "timestamp": system.date.format(qualified_value.timestamp, "yyyy-MM-dd'T'HH:mm:ss.SSSXXX") if qualified_value.timestamp is not None else None,
        })
    _log_success(operation)
    return {"json": {"ok": True, "values": values}}
except Exception, exc:
    _log_error(operation, "readBlocking failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

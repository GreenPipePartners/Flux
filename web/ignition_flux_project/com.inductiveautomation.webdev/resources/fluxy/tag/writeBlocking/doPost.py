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

operation = "Tag.writeBlocking"
DEFAULT_TIMEOUT_MS = 45000
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    tag_paths = payload.get("tagPaths") or payload.get("tag_paths")
    values = payload.get("values")
    timeout_ms = int(payload.get("timeoutMs") or payload.get("timeout_ms") or DEFAULT_TIMEOUT_MS)
    if not isinstance(tag_paths, list):
        return _bad_request("Request must include tagPaths list", _request_debug(request))
    if not isinstance(values, list):
        return _bad_request("Request must include values list", _request_debug(request))
    if len(tag_paths) != len(values):
        return _bad_request("tagPaths and values must have the same length")
    quality_codes = system.tag.writeBlocking(tag_paths, values, timeout_ms)
    qualities = []
    for index in range(len(tag_paths)):
        qualities.append({"tagPath": tag_paths[index], "quality": str(quality_codes[index])})
    _log_success(operation)
    return {"json": {"ok": True, "qualities": qualities}}
except Exception, exc:
    _log_error(operation, "writeBlocking failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

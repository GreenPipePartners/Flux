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


def _browse_result_to_dict(result):
    item = {}
    for key in ["name", "fullPath", "tagType", "dataType", "hasChildren"]:
        value = None
        try:
            value = result[key]
        except Exception:
            try:
                value = getattr(result, key)
            except Exception:
                pass
        if value is None:
            continue
        if key == "hasChildren":
            item[key] = bool(value)
        else:
            item[key] = str(value)
    return item

operation = "Tag.browse"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    path = payload.get("path") or payload.get("basePath") or payload.get("base_path")
    browse_filter = payload.get("filter") or {}
    if not isinstance(path, basestring):
        return _bad_request("Request must include path string", _request_debug(request))
    if not isinstance(browse_filter, dict):
        return _bad_request("filter must be an object", _request_debug(request))
    browse_results = system.tag.browse(path, browse_filter)
    results = [_browse_result_to_dict(result) for result in browse_results.getResults()]
    _log_success(operation)
    return {"json": {"ok": True, "results": results}}
except Exception, exc:
    _log_error(operation, "browse failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

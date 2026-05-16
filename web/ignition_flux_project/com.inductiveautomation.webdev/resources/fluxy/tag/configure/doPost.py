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

operation = "Tag.configure"
DEFAULT_COLLISION_POLICY = "o"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    base_path = payload.get("basePath") or payload.get("base_path")
    tags = payload.get("tags")
    collision_policy = payload.get("collisionPolicy") or payload.get("collision_policy") or DEFAULT_COLLISION_POLICY
    if not isinstance(base_path, basestring):
        return _bad_request("Request must include basePath string", _request_debug(request))
    if not isinstance(tags, list):
        return _bad_request("Request must include tags list", _request_debug(request))
    quality_codes = system.tag.configure(base_path, tags, collision_policy)
    qualities = []
    for index in range(len(quality_codes)):
        name = None
        if index < len(tags) and isinstance(tags[index], dict):
            name = tags[index].get("name")
        qualities.append({"name": name, "quality": str(quality_codes[index])})
    _log_success(operation)
    return {"json": {"ok": True, "qualities": qualities}}
except Exception, exc:
    _log_error(operation, "configure failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

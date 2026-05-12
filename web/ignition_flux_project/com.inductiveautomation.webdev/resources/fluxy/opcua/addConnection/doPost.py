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

operation = "OpcUa.addConnection"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    name = payload.get("name")
    description = payload.get("description") or ""
    discovery_url = payload.get("discoveryUrl") or payload.get("discovery_url")
    endpoint_url = payload.get("endpointUrl") or payload.get("endpoint_url")
    security_policy = payload.get("securityPolicy") or payload.get("security_policy") or "None"
    security_mode = payload.get("securityMode") or payload.get("security_mode") or "None"
    settings = payload.get("settings") or {}
    if not isinstance(name, basestring):
        return _bad_request("Request must include name string", _request_debug(request))
    if not isinstance(discovery_url, basestring):
        return _bad_request("Request must include discoveryUrl string", _request_debug(request))
    if not isinstance(endpoint_url, basestring):
        return _bad_request("Request must include endpointUrl string", _request_debug(request))
    if not isinstance(settings, dict):
        return _bad_request("settings must be an object", _request_debug(request))
    system.opcua.addConnection(
        str(name),
        str(description),
        str(discovery_url),
        str(endpoint_url),
        str(security_policy),
        str(security_mode),
        settings,
    )
    _log_success(operation)
    return {"json": {"ok": True, "name": name}}
except Exception, exc:
    _log_error(operation, "addConnection failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

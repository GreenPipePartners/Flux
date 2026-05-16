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

operation = "Util.getGatewayStatus"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    gateway_address = payload.get("gatewayAddress") or payload.get("gateway_address")
    connect_timeout = payload.get("connectTimeoutMillis") or payload.get("connect_timeout_millis")
    socket_timeout = payload.get("socketTimeoutMillis") or payload.get("socket_timeout_millis")
    bypass_cert_validation = payload.get("bypassCertValidation")
    if not isinstance(gateway_address, basestring):
        return _bad_request("Request must include gatewayAddress string", _request_debug(request))
    if connect_timeout is None and socket_timeout is None and bypass_cert_validation is None:
        status = system.util.getGatewayStatus(gateway_address)
    elif bypass_cert_validation is None:
        status = system.util.getGatewayStatus(gateway_address, int(connect_timeout or 5000), int(socket_timeout or 5000))
    else:
        status = system.util.getGatewayStatus(gateway_address, int(connect_timeout or 5000), int(socket_timeout or 5000), bool(bypass_cert_validation))
    _log_success(operation)
    return {"json": {"ok": True, "status": str(status)}}
except Exception, exc:
    _log_error(operation, "getGatewayStatus failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

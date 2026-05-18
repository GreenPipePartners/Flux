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

operation = "Util.audit"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    action = payload.get("action")
    if not isinstance(action, basestring):
        return _bad_request("Request must include action string", _request_debug(request))
    event_timestamp = payload.get("eventTimestamp") or payload.get("event_timestamp")
    if event_timestamp is not None:
        event_timestamp = system.date.fromMillis(long(event_timestamp))
    kwargs = {"action": action}
    optional = {
        "actionTarget": payload.get("actionTarget") or payload.get("action_target"),
        "actionValue": payload.get("actionValue") or payload.get("action_value"),
        "auditProfile": payload.get("auditProfile") or payload.get("audit_profile"),
        "actor": payload.get("actor"),
        "actorHost": payload.get("actorHost") or payload.get("actor_host"),
        "originatingSystem": payload.get("originatingSystem") or payload.get("originating_system"),
        "eventTimestamp": event_timestamp,
        "originatingContext": payload.get("originatingContext") or payload.get("originating_context"),
        "statusCode": payload.get("statusCode") or payload.get("status_code"),
    }
    for key, value in optional.items():
        if value is not None:
            kwargs[key] = value
    system.util.audit(**kwargs)
    _log_success(operation)
    return {"json": {"ok": True}}
except Exception, exc:
    _log_error(operation, "audit failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

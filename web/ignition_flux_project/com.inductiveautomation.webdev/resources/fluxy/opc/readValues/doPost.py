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


def _qualified_value(value):
    timestamp = value.getTimestamp()
    return {
        "value": value.getValue(),
        "quality": str(value.getQuality()),
        "timestamp": timestamp.getTime() if timestamp is not None else None,
    }


def _browse_tag(tag):
    item = {"raw": str(tag)}
    for key, method_name in [
        ("opcServer", "getOpcServer"),
        ("opcItemPath", "getOpcItemPath"),
        ("type", "getType"),
        ("displayName", "getDisplayName"),
        ("displayPath", "getDisplayPath"),
        ("dataType", "getDataType"),
    ]:
        try:
            value = getattr(tag, method_name)()
            item[key] = str(value) if value is not None else None
        except Exception:
            pass
    return item


def _browse_element(element):
    item = {"raw": str(element)}
    for key, method_name in [
        ("displayName", "getDisplayName"),
        ("elementType", "getElementType"),
        ("nodeId", "getNodeId"),
        ("serverName", "getServerName"),
        ("dataType", "getDataType"),
        ("datatype", "getDatatype"),
        ("description", "getDescription"),
    ]:
        try:
            value = getattr(element, method_name)()
            item[key] = str(value) if value is not None else None
        except Exception:
            pass
    return item

operation = "Opc.readValues"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    opc_server = payload.get("opcServer") or payload.get("opc_server")
    item_paths = payload.get("itemPaths") or payload.get("item_paths")
    if not isinstance(opc_server, basestring):
        return _bad_request("Request must include opcServer string", _request_debug(request))
    if not isinstance(item_paths, list):
        return _bad_request("Request must include itemPaths list", _request_debug(request))
    values = [_qualified_value(value) for value in system.opc.readValues(opc_server, item_paths)]
    _log_success(operation)
    return {"json": {"ok": True, "values": values}}
except Exception, exc:
    _log_error(operation, "readValues failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

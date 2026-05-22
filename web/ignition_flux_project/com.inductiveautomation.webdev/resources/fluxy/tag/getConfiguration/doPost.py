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


def _config_value(config, key):
    try:
        value = config[key]
    except Exception:
        try:
            value = getattr(config, key)
        except Exception:
            return None
    if value is None:
        return None
    if key in ["tagType", "dataType", "valueSource"]:
        text = str(value)
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1]
        return text
    return _value_to_wire(value)


def _config_to_dict(config):
    item = {}
    for key in [
        "name",
        "tagType",
        "valueSource",
        "dataType",
        "value",
        "tooltip",
        "documentation",
        "historyEnabled",
        "historyProvider",
        "historySampleMode",
        "historySampleRate",
        "historySampleRateUnits",
        "historyMinTimeBetweenSamples",
        "historyMinTimeUnits",
        "historicalDeadband",
        "historicalDeadbandMode",
        "historyMaxAge",
        "historyMaxAgeUnits",
    ]:
        value = _config_value(config, key)
        if value is not None:
            item[key] = value
    child_tags = _config_value(config, "tags")
    if child_tags is not None:
        item["tags"] = [_config_to_dict(child) for child in child_tags]
    return item

operation = "Tag.getConfiguration"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    path = payload.get("path") or payload.get("tagPath") or payload.get("tag_path")
    paths = payload.get("paths") or payload.get("tagPaths") or payload.get("tag_paths")
    recursive = bool(payload.get("recursive", False))
    if paths is not None:
        if not isinstance(paths, list):
            return _bad_request("paths must be a list", _request_debug(request))
        decoded_configs = []
        for current_path in paths:
            if not isinstance(current_path, basestring):
                return _bad_request("paths must contain path strings", _request_debug(request))
            for config in system.tag.getConfiguration(current_path, recursive):
                decoded_config = _config_to_dict(config)
                if "fullPath" not in decoded_config:
                    decoded_config["fullPath"] = current_path
                decoded_configs.append(decoded_config)
    else:
        if not isinstance(path, basestring):
            return _bad_request("Request must include path string", _request_debug(request))
        configs = system.tag.getConfiguration(path, recursive)
        decoded_configs = [_config_to_dict(config) for config in configs]
    _log_success(operation)
    return {"json": {"ok": True, "configs": decoded_configs}}
except Exception, exc:
    _log_error(operation, "getConfiguration failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

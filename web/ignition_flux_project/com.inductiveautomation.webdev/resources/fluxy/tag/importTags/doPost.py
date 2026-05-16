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

import os
import tempfile

operation = "Tag.importTags"
if not _auth_ok(request):
    return _unauthorized()
temp_path = None
try:
    _log_start(operation)
    payload = _json_body(request)
    tags = payload.get("tags")
    base_path = payload.get("basePath") or payload.get("base_path")
    collision_policy = payload.get("collisionPolicy") or payload.get("collision_policy") or "o"
    if tags is None:
        return _bad_request("Request must include tags", _request_debug(request))
    if not isinstance(base_path, basestring):
        return _bad_request("Request must include basePath string", _request_debug(request))
    if isinstance(tags, basestring):
        raw_json = tags
    else:
        raw_json = system.util.jsonEncode(tags)

    handle, temp_path = tempfile.mkstemp(suffix=".json", prefix="fluxy-import-tags-")
    os.close(handle)
    temp_file = open(temp_path, "w")
    try:
        temp_file.write(raw_json)
    finally:
        temp_file.close()

    quality_codes = system.tag.importTags(temp_path, base_path, collision_policy)
    qualities = []
    for quality_code in quality_codes:
        qualities.append({"quality": str(quality_code)})
    _log_success(operation)
    return {"json": {"ok": True, "qualities": qualities}}
except Exception, exc:
    _log_error(operation, "importTags failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}
finally:
    if temp_path is not None:
        try:
            os.remove(temp_path)
        except Exception:
            pass

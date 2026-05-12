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

operation = "Tag.query"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    provider = payload.get("provider")
    query = payload.get("query") or {}
    limit = payload.get("limit")
    continuation = payload.get("continuation")
    if not isinstance(provider, basestring):
        return _bad_request("Request must include provider string", _request_debug(request))
    if not isinstance(query, dict):
        return _bad_request("query must be an object", _request_debug(request))
    if continuation:
        query_results = system.tag.query(provider, query, int(limit or 0), continuation)
    elif limit is not None:
        query_results = system.tag.query(provider, query, int(limit))
    else:
        query_results = system.tag.query(provider, query)
    results = []
    for result in query_results:
        item = {}
        for key in ["path", "name", "tagType", "dataType", "quality", "valueSource", "value"]:
            value = None
            try:
                value = result[key]
            except Exception:
                try:
                    value = getattr(result, key)
                except Exception:
                    pass
            if value is not None:
                item[key] = str(value)
        if not item:
            item["raw"] = str(result)
        results.append(item)
    continuation_point = None
    try:
        continuation_point = query_results.continuationPoint
    except Exception:
        try:
            continuation_point = query_results.getContinuationPoint()
        except Exception:
            pass
    _log_success(operation)
    if continuation_point is not None:
        continuation_point = str(continuation_point)
    return {"json": {"ok": True, "results": results, "continuationPoint": continuation_point}}
except Exception, exc:
    _log_error(operation, "query failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

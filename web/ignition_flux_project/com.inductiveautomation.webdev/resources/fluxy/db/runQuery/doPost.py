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


def _dataset_to_wire(dataset):
    rows = []
    column_names = list(dataset.getColumnNames())
    for row_index in range(dataset.getRowCount()):
        row = []
        for column_name in column_names:
            row.append(dataset.getValueAt(row_index, column_name))
        rows.append(row)
    return {
        "rows": rows,
        "columns": column_names,
    }

operation = "Db.runQuery"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    query = payload.get("query")
    database = payload.get("database") or payload.get("datasource")
    tx = payload.get("tx")
    if not isinstance(query, basestring):
        return _bad_request("Request must include query string", _request_debug(request))
    if tx:
        result = system.db.runQuery(query, database or "", tx)
    elif database:
        result = system.db.runQuery(query, database)
    else:
        result = system.db.runQuery(query)
    result = _dataset_to_wire(result)
    _log_success(operation)
    return {
        "json": {
            "ok": True,
            "result": result,
            "resultSource": "ignition.dataset",
            "resultMessage": "Ignition Dataset serialized as columns/rows; Fluxy converted to row mappings",
        }
    }
except Exception, exc:
    _log_error(operation, "runQuery failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

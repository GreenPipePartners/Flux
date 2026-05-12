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
            value = dataset.getValueAt(row_index, column_name)
            if hasattr(value, "getTime"):
                value = value.getTime()
            elif value is not None and not isinstance(value, (basestring, int, long, float, bool)):
                value = str(value)
            row.append(value)
        rows.append(row)
    return {"rows": rows, "columns": column_names}

operation = "Util.queryAuditLog"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    audit_profile_name = payload.get("auditProfileName") or payload.get("audit_profile_name")
    if not isinstance(audit_profile_name, basestring):
        return _bad_request("Request must include auditProfileName string", _request_debug(request))
    start_date = payload.get("startDate") or payload.get("start_date")
    end_date = payload.get("endDate") or payload.get("end_date")
    if start_date is not None:
        start_date = system.date.fromMillis(long(start_date))
    if end_date is not None:
        end_date = system.date.fromMillis(long(end_date))
    result = system.util.queryAuditLog(
        audit_profile_name,
        start_date,
        end_date,
        payload.get("actorFilter") or payload.get("actor_filter"),
        payload.get("actionFilter") or payload.get("action_filter"),
        payload.get("targetFilter") or payload.get("target_filter"),
        payload.get("valueFilter") or payload.get("value_filter"),
        payload.get("systemFilter") or payload.get("system_filter"),
        payload.get("contextFilter") or payload.get("context_filter"),
    )
    _log_success(operation)
    return {"json": {"ok": True, "result": _dataset_to_wire(result), "resultSource": "ignition.dataset", "resultMessage": "Ignition Dataset serialized as columns/rows; Fluxy converted to row mappings"}}
except Exception, exc:
    _log_error(operation, "queryAuditLog failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

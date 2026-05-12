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


def _ui_response_to_wire(response):
    return {
        "warnings": [str(value) for value in response.getWarns()],
        "errors": [str(value) for value in response.getErrors()],
        "infos": [str(value) for value in response.getInfos()],
    }


def _user_to_wire(user):
    fields = {}
    for key in ["username", "firstname", "lastname", "email", "badge", "language", "notes", "schedule"]:
        try:
            value = user.get(key)
            if value is not None:
                fields[key] = str(value)
        except Exception:
            pass
    roles = []
    try:
        roles = [str(role) for role in user.getRoles()]
    except Exception:
        pass
    contact_info = []
    try:
        for contact in user.getContactInfo():
            contact_info.append(str(contact))
    except Exception:
        pass
    username = fields.get("username")
    if username is None:
        try:
            username = str(user.getUserName())
        except Exception:
            username = ""
    return {"username": username, "fields": fields, "roles": roles, "contactInfo": contact_info}


def _schedule_to_wire(schedule):
    return {
        "name": str(schedule.getName()),
        "description": str(schedule.getDescription()),
        "type": str(schedule.getType()),
        "observeHolidays": bool(schedule.isObserveHolidays()),
    }


def _holiday_to_wire(holiday):
    return {
        "name": str(holiday.getName()),
        "date": holiday.getDate().getTime(),
        "repeatAnnually": bool(holiday.isRepeatAnnually()),
    }


def _apply_user_payload(user, payload, include_password):
    fields = payload.get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError("fields must be an object")
    for key, value in fields.items():
        user.set(str(key), value)
    if include_password:
        password = payload.get("password")
        if not isinstance(password, basestring):
            raise ValueError("password string is required")
        user.set("password", password)
    roles = payload.get("roles") or []
    if not isinstance(roles, list):
        raise ValueError("roles must be a list")
    if roles:
        user.addRoles([str(role) for role in roles])
    contact_info = payload.get("contactInfo") or payload.get("contact_info") or {}
    if not isinstance(contact_info, dict):
        raise ValueError("contactInfo must be an object")
    if contact_info:
        user.addContactInfo(dict((str(key), str(value)) for key, value in contact_info.items()))
    return user

operation = "User.getSchedule"
if not _auth_ok(request):
    return _unauthorized()
try:
    _log_start(operation)
    payload = _json_body(request)
    schedule = system.user.getSchedule(payload.get("name"))
    _log_success(operation)
    return {"json": {"ok": True, "schedule": _schedule_to_wire(schedule)}}
except Exception, exc:
    _log_error(operation, "getSchedule failed", exc)
    return {"json": {"ok": False, "error": str(exc)}, "status": 500}

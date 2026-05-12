def doGet(request, session):
    return {"json": {"ok": True, "resource": "project/getProjectNames"}}


def opcua_connection(action, name, endpoint_url):
    if action == "remove":
        system.opcua.removeConnection(name)
        return {"removed": name}
    if action == "add":
        settings = {
            "ENABLED": True,
            "DISCOVERYURL": endpoint_url,
            "ENDPOINTURL": endpoint_url,
            "SECURITYPOLICY": "None",
            "SECURITYMODE": "None",
            "CERTIFICATEVALIDATIONENABLED": False,
            "CONNECTTIMEOUT": 5000,
            "ACKNOWLEDGETIMEOUT": 5000,
            "REQUESTTIMEOUT": 5000,
            "SESSIONTIMEOUT": 60000,
        }
        system.opcua.addConnection(name, "Flux Field OPC UA simulator", endpoint_url, endpoint_url, "None", "None", settings)
        return {"added": name}
    raise ValueError("Unsupported action: %s" % action)

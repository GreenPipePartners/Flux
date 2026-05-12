# Flux Windows Service Wrapper

The Windows service target is a Microsoft .NET Worker Service that supervises the Python Flux worker and reports status back to `flux.serve`.

Planned responsibilities:

- install and run as a native Windows Service
- start and monitor the Python Flux worker
- write Windows Event Log entries
- update Flux service heartbeats
- consume approved service commands from the Flux database
- restart the worker when it exits unexpectedly

The optimization protocol remains in Python under `flux.opt`; the C# wrapper owns Windows-native lifecycle behavior.

Development note: this project targets `net10.0`, so building requires a .NET 10 SDK. A runtime-only installation can execute published binaries but cannot run `dotnet build`.

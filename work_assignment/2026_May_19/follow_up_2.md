# Interface Review
## http://localhost:8000/
### Live Ignition Bridge
- Let's make this a smaller card, like 'Sim config', 'Latest Reads'
- It should have a Grey 'OFFLINE' status because it is not connected
- We should be able to connect to multiple ignition production environments, so we can make the card '0 Connected'
- It should be grey now because it is not connected
### Stale tag recovery
- This worked well. When there are no stale tags, this card should be hidden
### FieldAgent Devices
- This needs to be updated to SimServer
### Service Heartbeats
- Consolidate this into a smaller, summary card. Make it link to a service management page
### Latest Tag Snapshots
- This is superfluous to the smaller cards. Remove it


## http://localhost:8000/serve/
### .NET 10/systemd/commands
- Remove these cards
### Heartbeats
- Many of these have a 'Last Seen' time of several hours ago. What does Heartbeat mean here? We need to reconcile this

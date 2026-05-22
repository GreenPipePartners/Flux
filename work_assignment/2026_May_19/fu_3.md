# http://localhost:8000/
- The `Ignition bridges` pane should be updated to include `sim` ignition connections, in addition to production. So the interface should say:
"{x} Production Connections"
"{y} Simulator Connections"

# http://localhost:8000/
## Flux sim OPC-UA Servers
For `Start` and `Stop` buttons, add a triangle and square ascii character before the corresponding word

# http://localhost:8000/
## Ignition bridges
0 Production Connections -> Prod bridges
1 Simulator Connections -> Sim bridges

# http://localhost:8000/sim/
## Simulation Platform
- This is good

## Catalog and runtime
- 2 providers make sense to me, with the 23 devices, 6790 OPC tags. But it should be renamed 'Tag providers'
- 1 FieldAgent endpoint makes no sense to me..This needs to be '2 Sim Servers'
  - So does this mean we are currently simulating 9 devices and 548 field tags?

--- Last Sent ---
## http://localhost:8000/sim/
- I really like the `Flux.base` `Configure Import` button that expands the card. I would like the little green square at the top left to do the same, and I want that to become a pattern everywhere. I think we need to move to make most things collapsed-by-default, with a card summary, and then you click the green icon to expand the larger context. Is that feasible to implement without adding a large layer of complexity?
- If not, let's update Catalog and Runtime to function this way

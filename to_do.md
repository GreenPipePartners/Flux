# Architecture

                                                               ┏━━Flux━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
                                                               ┃  ╔═══════════════════╗     ╔═══════════════════╗        ┌──────────┐ ╔══════════╗ ┃
                                                               ┃  ║    Flux.live:     ║     ║    Flux.trace:    ║        │ Internal │ ║ Features ║ ┃
                                                               ┃  ║   light process   ║     ║    Power user     ║        └──────────┘ ╚══════════╝ ┃
                                                               ┃  ║   visualization   ║←─┐  ║   customizeable   ←──────────────────────────────    ┃
                                                               ┃  ║      module       ║  │  ║  modern charting  ║                             │    ┃
                                                               ┃  ║                   ║  │  ║                   ║                             │    ┃
                                                               ┃  ╚═════════════════↑═╝  │  ╚═════════↑═════════╝                             │    ┃
                                                               ┃                    │    │            │              ┌────────────────────┐   │    ┃
                                                               ┃                    │    │  ┌─────────│─────────┐    │   Configurator:    │   │    ┃
                                                               ┃                    │    │  │                   │    │    - Flux.trace    │   │    ┃
                                                               ┃                    │    │  │     Flux.web:     ─────→    - Flux.live     │   │    ┃
                                                               ┃                    │    └──│   Client portal   │    │    - Flux.sim      │   │    ┃
                                                               ┃                    │       │                   │    │    - Flux.serve    │   │    ┃
                                                               ┃                    │       │                   │    │    - Flux.opt      │   │    ┃
                                                               ┃                    │       └──────↑─────────↑──┘    └────────────────────┘   │    ┃
                                                               ┃                    │              │         │                                │    ┃
                             ┌────────────────┐  ┌───────────┐ ┃  ╔═══════════╗   ┌─│──────────────│──┐    ┌─│─────────────────┐┌───────────┐ │    ┃
                             │                │  │           │ ┃  ║           ║   │                   │    │    Flux.base:     ││ Flux.opt: │ │    ┃
                             │    Ignition    │  │           │ ┃  ║           ║   │    Flux.serve:    ────→│     Postgres      ││ Live View │ │    ┃
                             │   Production   ←──│           │────║           ║──── Worker Servicing  │──┐──  Datastore for    ││   cache   │ │    ┃
                             │  Environment   ───│           │────║           ║───→                   │ ││ │  all persistant   ││ optimizer │ │    ┃
                             │                │  │           │ ┃  ║  fluxy:   ║   │                   │ ││ │      objects      ││           │ │    ┃
                             └────────────────┘  │  WebDev:  │ ┃  ║  python   ║   └───────────────────┘ ││ └───────────────────┘└───────────┘ │    ┃
                                                 │ Ignition  │ ┃  ║    for    ║                         ││                                    │    ┃
                             ┌────────────────┐  │  Module   │ ┃  ║ ignition  ║   ╔═══════════════════╗ ││  ┌───────────────────┐             │    ┃
                             │                │  │           │ ┃  ║           ║   ║                   ║ ││  │                   │             │    ┃
                             │    Ignition    ←──│           │────║           ║────     Flux.sim:     ║ ││  │    Flux.plane:    │             │    ┃
                             │  Development   ───│           │────║           ║───→  Dev Environment  ║←┘└─→│  Historical Data  │ ─────────────    ┃
                             │  Environment   │  │           │ ┃  ║           ║   ║      Builder      ║     │ Cache & Recovery  │                  ┃
                             │                │  │           │ ┃  ║           ║   ║                   ║     │                   │                  ┃
                             └────────────────┘  └───────────┘ ┃  ╚═══════════╝   ╚═══════════════════╝     └───────────────────┘                  ┃
                                                               ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
- fluxy is the Python/Ignition bridge through the Ignition WebDev module.
- fluxy talks to both Ignition production and development environments.
- Flux.serve is the worker/service execution layer.
- Flux.web is the client portal and configurator surface.
- Flux.base is Postgres-backed persistence for configuration/state.
- Flux.sim is the dev environment builder and owns simulated device/tag domain configuration.
- FieldAgent is the OPC-UA runtime adapter process supervised by Flux.serve; it services materialized Flux.sim devices but does not own the simulation domain.
- Flux.trace is the power-user customizable modern charting layer.
- Flux.live is the lightweight process visualization layer.
- Flux.plane handles historical data cache/recovery.
- Flux.opt handles live-view cache optimization.
- Configuration flows through Flux.web into the configurator for trace, live, sim, serve, and opt.
- Internal features feed into the higher-level Flux modules, especially around Flux.trace.

# Flux.web
## Interface
### localhost:8000 (home)
- Status indicates "ATTENTION NEEDED" (good)
  - It indicates 24/8052 tags online. However, this is not correct. The tags are "stale" bad_notfound, meaning they don't exist in ignition. 
  - How does this functionally differ from "missing/no read" tags? Seems these should be the stale
  - If they are different, we need to be explicit why
- Add a device status checker on the front page

# Flux.base
## Runtime tags
- Need to build a distinction in tag types
  - Production|Runtime tags, read from a production ignition gateway.
    - Simulation tags, built by Flux.sim
      - Relationship model looks like: 
      - "Device"|Flux.sim.device -> This should be a distinct instance of an OPC-UA server.
        - device/tag domain configuration is owned by Flux.sim
        - desired and materialized runtime configuration details live in Flux.base
        - Flux.serve is responsible for running one FieldAgent OPC-UA adapter process for each materialized runtime device

# Flux.serve
- Build services to run distinct materialized Flux.sim.device OPC-UA servers through one supervised FieldAgent adapter process per device
- Build closed-loop tests to verify this
  - Build device | configure device on ignition through fluxy | build trial tag OPC tag | read tag | wait for tag to change value | read again to confirm tag change | delete tag | read tag (verify gone) | delete device
    - make naming of device test-specific to reduce chance of collision
- Flux.sim.device should mirror device types based on the work being done in Flux.sim to generate various device type structures
- Current limitation: FieldAgent is still the implicit adapter executable in parts of the code/docs; the target architecture is explicit Flux.sim domain ownership, Flux.base persistence, Flux.serve supervision, and fluxy Ignition configuration.


# Flux.sim
## devices
- Add modes for devices
  - Default to a standard mode, where everything works well
  - Want to have the ability to operate in a "slow network" response mode, where the device takes {time} to respond to requests
- Add a new strategy pattern configuration for how a tag is addressed for a device
  - e.g. a "logix" device will have a "Local" address mapping utility, where we incorporate ":" into the addressing for local I/O, but it also has array tags which will be addressed differently
  - I have multiple sets of tag data in `tag_data/`. This should be a reference. 
    - `tag_02 devices.txt`|`tag_05 devices.context` lists devices for that tag provider, and device type (ACM02 is a dedicated OPC-UA server, which collects multiple devices. This will be considered a "device" in our context)
    - `tag_05.json` has the tags for that tag provider
    - `tag02.json` has the tags for that tag provider
    - `tag_05` has more PLC/logix devices
    - `tag_02` has more server-based tags
    - Use these as references for building out tags with appropriate strategies (ACM-based strategies, logix-based strategies, etc.)
      - This brings up a good point that our strategies should be based on driver probably, identified and categorized as a relationship in Flux.base
## ignition parser
- Add a formal device and tag parser 
  - these may exist already? Check our solution for things like this first, as we did ingest `tag02.json` previously.
  - if it exists and is not formalized in our architecture, make it formalized
  - These functions should work by ingesting tag exports (I think we will need to prompt for what the device type is normally, though)
  - We should also have a means to extract this from a connected production Interface
    - Build an end-to-end test, where we parse this information from tag_02, generate an OPC-UA server simulation of these tags, configure these devices and tags in the local ignition interface, and then export them and check them against our source tags
## tag simulation modes
- This should be a distinct strategy pattern solution, likely kept in its own directory, e.g. Flux.sim.tag_mode
- We will want to be able to simulate different tag modes, and this was started previously, so check the existing infrastructure
  - e.g. slow-response-tag (configure an {n} second response time)
  - e.g. ignore-write-tag (we write to the tag, and we ignore the request)
  - e.g. write-to-other-tag-response (we write e.g. 1 to a tag, and it writes e.g. 10 to {other_tag})
  - build out these cases, and build close-loop tests for them

# Proceed Autonomously
- This work is intended to go forward without interruption to the best of your ability to completion
- If you are tempted to pause and give a status update, don't. Continue until a task is completed.
- You may run into a trial expired error. If so, run the activate ignition script to attempt to clear it
- Bias to work to completion
- parse work into subworkers where it makes sense, and you act as orchastrator. You help negotiate interfaces, and determine needs amongst workers
- As changes are incorporated, do many stops with integrated testing to the best of your ability to ensure we don't break things along the way, or if we do break things, we fix them as we o
- Build tests!!!! We're going to forget as we go, so the better we can build tests (especially close-loop tests where we can clean up after ourselves), the more we can continue to build without fear of breaking
- Tests are our scaffolding

# Feedback from your questions
> Should FluxTraceNavWells runtime tags be excluded from live stale health, or should a worker populate LatestTagValue for them?
  - Yes, this was a trial stress test. I want to keep the logic for now to be able to reproduce the stress test without much fussing, but this should not be an interface display
> Should Flux.sim.device mean one OPC-UA server process per device, or one server process hosting many simulated devices?
  - One OPC-UA server process per device
> Should tag export parsing target tag_data/ only first, or also live extraction from production Ignition in the first pass?
  - Let's successfully complete ingestion of `tag_data/` first, and if this feels strong, with testing proving the implementation, let's proceed to a full feedback process, using our sim ignition as a production ignition (dual purposing)

# overview
- We are going to build an adjacent server to the Ignition platform. 
- It's a complement to Ignition Perspective. 
- Where Perspective updates live tag values, I want to build a parallel server structure. 
- This solution will query data in bulk from an ignition tag provider every 10-90 seconds (configurable), and that data can be rendered by a django/htmx platform and displayed to a user. 
  - The intended improvement is reduced load time by way of simpler interface + less package delivery. 
  - This will benefit field operations by making data very quickly captured, and eliminates network traffic on websocket traffic. 
- Part of this is adding in quick chart visibility, adapting from an existing history provider. A key feature is that I will want some visual way to cue readers that the data presented, after some amount of time, is stale and should be reloaded if there is a need for updated information. 
- I need: tables, display fields on cards, and charts, at a minimum.
- I want segmentation of trends, as this is heavy traffic usage. So we should only send chart.js when sent to that specific service call
- My plan is to intermittently query tag qualified values and place them in a dedicated database structure. The application then pulls data from queries rather than requesting tag reads.
- Want to have alarm journaling, as well, but not live alarming, as that would require websockets (or similar?)
- Will include active directory integration, with multiple roles from active directory dictating solution access
- Design the django app to be postgres native by default
- Preserve the single-accent terminal/industrial visual language in Flux. Legacy Drew migration workflow, models, upload handling, and conversion concepts are not part of Flux.

# interface
- Flux will have a set of tags provided to it in the database
- This database will be shared by Ignition and Flux
- There will be a script applied to the ignition application, with access to the associate tag database
  - This script will read the tags in the flux database and perform a readBlocking based in its contents. The results will be written to the flux database
  - There will be multiple schedules that the tags will be assigned to. e.g. Schedule A will be a 5 second schedule, schedule B will be a 10 second schedule, schedule C will be a 30 second schedule (C by default)
  - The ignition script will view deploy tag reads based on the schedule every 5 seconds
  - We may end up load balancing depending on performance, but that I don't think is an initial problem to solve

# Admin
- Flux needs an administration interface
- This will be evolving, but at a minimum, we will need to add configuration to apply active directory
- We also need to add credentials to connect to the ignition & historical database for read-only access to the alarm journaling and historical data capture

# Target screens
- I have included a backup perspective project for the first project we're going to trial complementing with Flux. This should be used as a for-instance case to build a general, packageable software solution for multiple customers. Notable things we're going to want to replicate are:
  - Pages/Equipment Summary
    - Here is another example of a table to be reproduced
  - Pages/Pad overview
    - Here, we are replicating cards which display live data per equipment
  - Pages/Plunger Control
    - The core feature to reproduce here is the table. Currently, when selecting rows on this table, there is a dock that pops up for control of a given plunger. In the updated model, I expect we will open a separate window in perspective to do the control

# Software License model
- I want to develop this as a BSL license. I think after a year, the version released should become open source. If we find good ways to limit use without licenses, we should consider that, but first priority should be to get this up, running, and working

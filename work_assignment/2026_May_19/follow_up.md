# Interface Review
## http://localhost:8000/sim/
### First card: FLUX.SIM
- There is a card at the top right that says "SCHEDULED VALUES". That has no meaning to me. Let's have this be a highest level 'Online/Trial/Unlicensed' card with Green/Green/Grey schemes
### Second card: SUPERVISOR STATUS
- Good `Imported Catalog` card
- `COVERAGE` card is now redundant
- `Materialized Runtime` needs to be `Sim Runtime`, and we need to link to a control config to turn devices on/off
### Third card: Generate Provider Model
- Let's make this a dropdown configuration instead of showing everything by default. Once we've imported a structure, we don't want to look at it anymore really
### 1s/5s/10s status cards
- Lets remove this for now
### Imported Provider
- Good menu.
### Simulation Selection
- This seems confusing to have before a provider is selected. I think this is legacy, and everything associate it probably needs removed?
### Tag Behavior
- We will need a menu like this, but it doesn't belong here. This should be a selection option from a cog widget to the right of a tag in the tree section e.g. here:
  - 0 provider branch selection(s). Export selected OPC leaf paths at /sim/imported/selected-paths.json?provider=Tag_02.
  - The menu as it is today is way too bulky
### Simulated Tags
- This should be a link from a summary in `SUPERVISOR STATUS`, not a window here
### History Backfills
- This should be a link from a summary in `SUPERVISOR STATUS`, not a window here

## http://localhost:8000/
### Runtime config | Field config
- Consolidate together, one card called "Sim config"
### FieldAgent
- This is deprecated now, I think. Remove this.

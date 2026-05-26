# Spot

Flux Spot is the current-state card surface formerly called Flux Live.

Spot renders cached runtime values from Flux storage. It must not bind the browser directly to Ignition tags or make HTMX polling responsible for backend freshness.

```text
Flux.serve worker -> Flux.opt sampler -> LatestTagValue + TagSample -> Flux.spot cards
```

The historical `flux.live` Django app label and tables remain in place during the compatibility migration to avoid unsafe database churn.

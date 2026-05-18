import { createTracePlot, hoverBoldLinePlugin, resizeTracePlot, setTracePlotPayload } from "./chart.js";
import { createTraceAnnotationController } from "./annotations.js";
import { alignTracePayload, nearestTraceValues, traceSeriesFromPayload } from "./data.js";
import { closestTraceIndex, dragPanPlugin, isInsideTraceChart, wheelPanZoomPlugin } from "./interactions.js";
import { pinnedTraceMarkdown, renderPinnedTraceMarkers, traceOverlayPlugin } from "./markers.js";

const payload = JSON.parse(document.getElementById("trace-data").textContent);
const chartElement = document.querySelector("[data-trace-chart]");
const markerPanel = document.querySelector("[data-pinned-trace-table]");
const status = document.querySelector("[data-trace-status]");
let traceSeries = traceSeriesFromPayload(payload);
const pinnedTraceMarkers = [];
const traceAnnotations = [];
let suppressNextClick = false;
let aligned = alignTracePayload(traceSeries);
let activeSetIndex = payload.setIndex || 1;
let activeProfileKey = payload.profileKey || "";
let activeWindowMinutes = payload.windowMinutes || Math.round((payload.windowDays || 1) * 1440);
let activeStepMinutes = payload.stepMinutes || 1;

function traceStatus(message) {
  if (status) status.textContent = message;
}

function renderMarkers() {
  renderPinnedTraceMarkers({ markerPanel, pinnedTraceMarkers, traceAnnotations, traceSeries, addMarkerAnnotation: annotationController.addMarkerAnnotation, submitMarkerAnnotation: annotationController.submitMarkerAnnotation });
}

function pinTraceMarker(index) {
  if (index === null || index === undefined || !aligned.times[index]) {
    traceStatus("Chart click received, but no trace sample was found near that click.");
    return;
  }
  const pinnedAt = new Date(aligned.data[0][index] * 1000).toISOString();
  const markerId = pinnedTraceMarkers.length + 1;
  pinnedTraceMarkers.push({ id: markerId, pinnedAt, values: nearestTraceValues(traceSeries, aligned, index) });
  renderMarkers();
  plot.redraw();
  traceStatus(`Pinned marker (${markerId}) at ${new Date(pinnedAt).toLocaleString()}.`);
}

const plot = createTracePlot({
  element: chartElement,
  data: aligned.data,
  series: traceSeries,
  plugins: [
    traceOverlayPlugin({ pinnedTraceMarkers, traceAnnotations }),
    hoverBoldLinePlugin({ getTraceSeries: () => traceSeries }),
    wheelPanZoomPlugin(),
    dragPanPlugin((dragging) => { suppressNextClick = dragging; }),
  ],
});
const annotationController = createTraceAnnotationController({
  chartElement,
  traceAnnotations,
  pinnedTraceMarkers,
  traceStatus,
  renderMarkers,
  redraw: () => plot.redraw(),
  getState: () => ({ activeProfileKey, aligned, traceSeries }),
});
window.__fluxTraceDebug = { plot, aligned, pinnedTraceMarkers, traceSeries };
installTraceSetCycling();
installTraceLiveRefresh();
annotationController.loadPersistedAnnotations();

document.addEventListener("pointerup", (event) => {
  if (!isInsideTraceChart(chartElement, event.clientX, event.clientY)) return;
  if (suppressNextClick) return;
  if (plot.select.width > 3) return;
  pinTraceMarker(closestTraceIndex(plot, event.clientX));
}, true);

document.querySelector("[data-reset-trace-range]").addEventListener("click", () => {
  plot.setScale("x", { min: null, max: null });
});
document.querySelector("[data-clear-pinned-traces]").addEventListener("click", (event) => {
  event.preventDefault();
  event.stopPropagation();
  pinnedTraceMarkers.length = 0;
  traceAnnotations.length = 0;
  renderMarkers();
  plot.redraw();
});
document.querySelector("[data-copy-pinned-traces]").addEventListener("click", async (event) => {
  event.preventDefault();
  event.stopPropagation();
  if (!pinnedTraceMarkers.length) return;
  await navigator.clipboard.writeText(pinnedTraceMarkdown(pinnedTraceMarkers, traceSeries));
});
document.querySelector("[data-send-trace-annotations]").addEventListener("click", async (event) => {
  event.preventDefault();
  event.stopPropagation();
  await annotationController.sendPendingAnnotations();
});
window.addEventListener("resize", () => resizeTracePlot(plot, chartElement));

function installTraceSetCycling() {
  const cycleUrl = chartElement.dataset.traceCycleUrl;
  const setCount = Number(chartElement.dataset.traceSetCount || 0);
  if (!cycleUrl || !setCount) return;
  document.querySelector("[data-trace-prev-set]")?.addEventListener("click", () => cycleTraceSet(cycleUrl, setCount, -1));
  document.querySelector("[data-trace-next-set]")?.addEventListener("click", () => cycleTraceSet(cycleUrl, setCount, 1));
  document.addEventListener("keydown", async (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    await cycleTraceSet(cycleUrl, setCount, direction);
  });
}

function installTraceLiveRefresh() {
  const cycleUrl = chartElement.dataset.traceCycleUrl;
  const refreshSeconds = Number(chartElement.dataset.traceLiveRefreshSeconds || 0);
  if (!cycleUrl || !refreshSeconds) return;
  window.setInterval(() => refreshActiveTraceSet(cycleUrl), refreshSeconds * 1000);
}

async function cycleTraceSet(cycleUrl, setCount, direction) {
  const nextSet = ((activeSetIndex - 1 + direction + setCount) % setCount) + 1;
  await loadTraceSet(cycleUrl, nextSet);
}

async function loadTraceSet(cycleUrl, setIndex) {
  traceStatus(`Loading source ${setIndex}...`);
  const response = await fetch(tracePayloadUrl(cycleUrl, setIndex));
  const payload = await response.json();
  if (payload.traceError) {
    traceStatus(`Trace query failed: ${payload.traceError}`);
    return;
  }
  activeSetIndex = payload.traceChart.setIndex || setIndex;
  applyTracePayload(payload.traceChart, { clearMarkers: true });
  await annotationController.loadPersistedAnnotations();
  const label = document.querySelector("[data-trace-set-label]");
  if (label) label.textContent = payload.traceChart.setLabel || `Source ${activeSetIndex}`;
  traceStatus(`Loaded ${payload.traceChart.setLabel || `source ${activeSetIndex}`}.`);
}

async function refreshActiveTraceSet(cycleUrl) {
  const response = await fetch(tracePayloadUrl(cycleUrl, activeSetIndex));
  const payload = await response.json();
  if (payload.traceError) {
    traceStatus(`Live refresh failed: ${payload.traceError}`);
    return;
  }
  activeSetIndex = payload.traceChart.setIndex || activeSetIndex;
  applyTracePayload(payload.traceChart, { clearMarkers: false });
  traceStatus(`Live refresh ${new Date().toLocaleTimeString()} (${payload.traceChart.setLabel || `source ${activeSetIndex}`}).`);
}

function tracePayloadUrl(cycleUrl, setIndex) {
  const params = new URLSearchParams({
    set: String(setIndex),
    window_minutes: String(activeWindowMinutes),
    step_minutes: String(activeStepMinutes),
  });
  return `${cycleUrl}?${params.toString()}`;
}

function applyTracePayload(traceChart, { clearMarkers }) {
  traceSeries = traceSeriesFromPayload(traceChart);
  activeProfileKey = traceChart.profileKey || activeProfileKey;
  activeWindowMinutes = traceChart.windowMinutes || Math.round((traceChart.windowDays || 1) * 1440);
  activeStepMinutes = traceChart.stepMinutes || activeStepMinutes;
  aligned = alignTracePayload(traceSeries);
  if (clearMarkers) {
    pinnedTraceMarkers.length = 0;
    traceAnnotations.length = 0;
    renderMarkers();
  }
  setTracePlotPayload(plot, traceChart, aligned.data, traceSeries);
  window.__fluxTraceDebug = { plot, aligned, pinnedTraceMarkers, traceSeries };
}

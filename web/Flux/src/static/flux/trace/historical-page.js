import { createTracePlot, resizeTracePlot } from "./chart.js";
import { alignTracePayload, nearestTraceValues, traceSeriesFromPayload } from "./data.js";
import { closestTraceIndex, dragPanPlugin, isInsideTraceChart, wheelPanZoomPlugin } from "./interactions.js";
import { annotationText, pinnedTraceMarkdown, renderPinnedTraceMarkers, traceOverlayPlugin } from "./markers.js";

const payload = JSON.parse(document.getElementById("trace-data").textContent);
const chartElement = document.querySelector("[data-trace-chart]");
const markerPanel = document.querySelector("[data-pinned-trace-table]");
const status = document.querySelector("[data-trace-status]");
const traceSeries = traceSeriesFromPayload(payload);
const pinnedTraceMarkers = [];
const traceAnnotations = [];
let suppressNextClick = false;
let aligned = alignTracePayload(traceSeries);

function traceStatus(message) {
  if (status) status.textContent = message;
}

function addMarkerAnnotation(marker) {
  const text = annotationText(marker);
  if (!text) return;
  traceAnnotations.push({ markerId: marker.id, pinnedAt: marker.pinnedAt, text });
  plot.redraw();
}

function renderMarkers() {
  renderPinnedTraceMarkers({ markerPanel, pinnedTraceMarkers, traceSeries, addMarkerAnnotation });
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
  plugins: [traceOverlayPlugin({ pinnedTraceMarkers, traceAnnotations }), wheelPanZoomPlugin(), dragPanPlugin((dragging) => { suppressNextClick = dragging; })],
});
window.__fluxTraceDebug = { plot, aligned, pinnedTraceMarkers, traceSeries };

document.addEventListener("pointerup", (event) => {
  if (!isInsideTraceChart(chartElement, event.clientX, event.clientY)) return;
  if (suppressNextClick) return;
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
window.addEventListener("resize", () => resizeTracePlot(plot, chartElement));

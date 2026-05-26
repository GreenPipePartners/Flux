import { createTracePlot, resizeTracePlot } from "./chart.js";
import { alignTracePayload, mergeLiveSeries, newestTraceTime, traceSeriesFromPayload } from "./data.js?v=trace-shared-x-2";
import { dragPanPlugin, wheelPanZoomPlugin } from "./interactions.js";

const payload = JSON.parse(document.getElementById("trace-live-data").textContent);
const chartElement = document.querySelector("[data-trace-live-chart]");
const liveTraceData = traceSeriesFromPayload(payload);
const pollMilliseconds = Number(chartElement.dataset.pollSeconds) * 1000;
const windowMilliseconds = Number(chartElement.dataset.windowMinutes) * 60 * 1000;
const samplesUrl = chartElement.dataset.samplesUrl;
let latestReadAt = payload.latestReadAt;
let isPaused = false;
let aligned = alignTracePayload(liveTraceData);

const livePlot = createTracePlot({
  element: chartElement,
  data: aligned.data,
  series: liveTraceData,
  plugins: [wheelPanZoomPlugin(), dragPanPlugin()],
});
updateLiveTraceDebug();

function currentRange() {
  return livePlot.scales.x.min === null || livePlot.scales.x.max === null ? null : [livePlot.scales.x.min, livePlot.scales.x.max];
}

function isAtRightEdge() {
  const range = currentRange();
  const newest = newestTraceTime(aligned);
  if (!range || newest === null) return true;
  return Math.abs(range[1] * 1000 - newest) <= pollMilliseconds * 1.5;
}

function rightEdgeRange(newest) {
  return { min: (newest - windowMilliseconds) / 1000, max: newest / 1000 };
}

const initialNewest = newestTraceTime(aligned);
if (initialNewest !== null) livePlot.setScale("x", rightEdgeRange(initialNewest));

async function pollLiveTrace() {
  if (isPaused) return;
  const followRightEdge = isAtRightEdge();
  const preservedRange = currentRange();
  const response = await fetch(`${samplesUrl}?since=${encodeURIComponent(latestReadAt || "")}`);
  if (!response.ok) return;
  const nextPayload = await response.json();
  if (!nextPayload.series.length) return;
  mergeLiveSeries(liveTraceData, nextPayload);
  if (nextPayload.latestReadAt) latestReadAt = nextPayload.latestReadAt;
  aligned = alignTracePayload(liveTraceData);
  updateLiveTraceDebug();
  livePlot.setData(aligned.data);
  const newest = newestTraceTime(aligned);
  if (followRightEdge && newest !== null) {
    livePlot.setScale("x", rightEdgeRange(newest));
  } else if (preservedRange) {
    livePlot.setScale("x", { min: preservedRange[0], max: preservedRange[1] });
  }
}

function updateLiveTraceDebug() {
  window.__fluxLiveTraceDebug = { plot: livePlot, liveTraceData, aligned, pollLiveTrace };
}

window.setInterval(pollLiveTrace, pollMilliseconds);
document.querySelector("[data-live-trace-toggle]").addEventListener("click", (event) => {
  isPaused = !isPaused;
  event.currentTarget.textContent = isPaused ? "Resume" : "Pause";
  document.querySelector("[data-live-trace-status]").textContent = isPaused ? "Polling paused." : `Polling every ${chartElement.dataset.pollSeconds}s. Wheel zooms; drag pans.`;
});
document.querySelector("[data-reset-trace-range]").addEventListener("click", () => {
  const newest = newestTraceTime(aligned);
  if (newest !== null) livePlot.setScale("x", rightEdgeRange(newest));
});
window.addEventListener("resize", () => resizeTracePlot(livePlot, chartElement));

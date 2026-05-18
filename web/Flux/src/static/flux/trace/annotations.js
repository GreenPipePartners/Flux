import { nearestTraceValues } from "./data.js";


export function createTraceAnnotationController({ chartElement, traceAnnotations, pinnedTraceMarkers, traceStatus, renderMarkers, redraw, getState }) {
  function nextAnnotationSequence() {
    return traceAnnotations.reduce((highest, annotation) => Math.max(highest, Number(annotation.sequence || 0)), 0) + 1;
  }

  function addMarkerAnnotation(marker) {
    marker.annotationDraft = true;
    renderMarkers();
    traceStatus(`Add a local annotation below marker (${marker.id}), then use Send Annotations to save it to Ignition.`);
  }

  function submitMarkerAnnotation(marker, text) {
    if (!text) return;
    traceAnnotations.push({ localId: crypto.randomUUID(), sequence: nextAnnotationSequence(), markerId: marker.id, pinnedAt: marker.pinnedAt, text, saved: false });
    marker.annotationDraft = false;
    renderMarkers();
    redraw();
    traceStatus(`Added local annotation below marker (${marker.id}). Use Send Annotations to save it to Ignition.`);
  }

  async function sendPendingAnnotations() {
    const pending = traceAnnotations.filter((annotation) => !annotation.saved);
    if (!pending.length) {
      traceStatus("No local annotations to send.");
      return;
    }
    traceStatus(`Sending ${pending.length} annotation${pending.length === 1 ? "" : "s"} to Ignition...`);
    let savedCount = 0;
    for (const annotation of pending) {
      if (await saveMarkerAnnotation(annotation)) savedCount += 1;
    }
    renderMarkers();
    redraw();
    traceStatus(`Sent ${savedCount} annotation${savedCount === 1 ? "" : "s"} to Ignition.`);
  }

  async function saveMarkerAnnotation(annotation) {
    const annotationUrl = chartElement.dataset.traceAnnotationUrl;
    if (!annotationUrl) return false;
    const state = getState();
    const response = await fetch(annotationUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(chartElement) },
      body: JSON.stringify({
        markerId: annotation.markerId,
        sequence: annotation.sequence,
        pinnedAt: annotation.pinnedAt,
        text: annotation.text,
        profileKey: state.activeProfileKey,
        paths: state.traceSeries.map((series) => series.fullPath).filter(Boolean),
      }),
    });
    const responsePayload = await jsonResponsePayload(response);
    if (!response.ok || !responsePayload.ok) {
      traceStatus(`Annotation save failed: ${responsePayload.error || response.statusText}`);
      return false;
    }
    Object.assign(annotation, responsePayload.annotation || {}, { sequence: annotation.sequence, saved: true });
    return true;
  }

  async function loadPersistedAnnotations() {
    const queryUrl = chartElement.dataset.traceAnnotationQueryUrl;
    const state = getState();
    if (!queryUrl || !state.traceSeries.length || !state.aligned.data[0]?.length) return;
    const response = await fetch(queryUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(chartElement) },
      body: JSON.stringify({
        profileKey: state.activeProfileKey,
        paths: state.traceSeries.map((series) => series.fullPath).filter(Boolean),
        startTime: state.aligned.data[0][0] * 1000,
        endTime: state.aligned.data[0][state.aligned.data[0].length - 1] * 1000,
      }),
    });
    const responsePayload = await jsonResponsePayload(response);
    if (!response.ok || !responsePayload.ok) {
      traceStatus(`Annotation recovery failed: ${responsePayload.error || response.statusText}`);
      return;
    }
    applyPersistedAnnotations(responsePayload.annotations || []);
  }

  function applyPersistedAnnotations(annotations) {
    let recoveredCount = 0;
    for (const annotation of annotations) {
      if (traceAnnotations.some((existing) => existing.id === annotation.id || existing.localId === annotation.localId)) continue;
      const marker = recoveredMarkerForAnnotation(annotation);
      traceAnnotations.push({ ...annotation, sequence: annotation.sequence || nextAnnotationSequence(), markerId: marker.id, saved: true });
      recoveredCount += 1;
    }
    if (!recoveredCount) return;
    renderMarkers();
    redraw();
    traceStatus(`Recovered ${recoveredCount} saved annotation${recoveredCount === 1 ? "" : "s"} from Ignition.`);
  }

  function recoveredMarkerForAnnotation(annotation) {
    const state = getState();
    const existing = pinnedTraceMarkers.find((marker) => marker.pinnedAt === annotation.pinnedAt);
    if (existing) return existing;
    const timestamp = Date.parse(annotation.pinnedAt) / 1000;
    let bestIndex = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < state.aligned.data[0].length; index += 1) {
      const distance = Math.abs(state.aligned.data[0][index] - timestamp);
      if (distance < bestDistance) {
        bestIndex = index;
        bestDistance = distance;
      }
    }
    const marker = {
      id: pinnedTraceMarkers.length + 1,
      pinnedAt: new Date(state.aligned.data[0][bestIndex] * 1000).toISOString(),
      values: nearestTraceValues(state.traceSeries, state.aligned, bestIndex),
    };
    pinnedTraceMarkers.push(marker);
    return marker;
  }

  return { addMarkerAnnotation, submitMarkerAnnotation, sendPendingAnnotations, loadPersistedAnnotations };
}


export function csrfToken(chartElement) {
  if (chartElement.dataset.traceCsrfToken) return chartElement.dataset.traceCsrfToken;
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}


export async function jsonResponsePayload(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (_error) {
    return { ok: false, error: text ? text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 180) : response.statusText };
  }
}

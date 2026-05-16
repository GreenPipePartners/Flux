import { traceColors } from "./chart.js";

export function middleEllipsis(value, limit = 15) {
  const text = String(value);
  if (text.length <= limit) return text;
  const keep = limit - 1;
  const left = Math.ceil(keep / 2);
  const right = Math.floor(keep / 2);
  return `${text.slice(0, left)}...${text.slice(text.length - right)}`;
}

export function traceHeader(traceSeries, series) {
  const duplicateName = traceSeries.some((other) => other.traceIndex !== series.traceIndex && other.name === series.name);
  return duplicateName ? series.fullPath : series.name;
}

export function renderPinnedTraceMarkers({ markerPanel, pinnedTraceMarkers, traceSeries, addMarkerAnnotation }) {
  markerPanel.replaceChildren();
  if (!pinnedTraceMarkers.length) {
    const emptyMessage = document.createElement("p");
    emptyMessage.className = "muted";
    emptyMessage.textContent = "No pinned traces yet.";
    markerPanel.appendChild(emptyMessage);
    return;
  }

  const table = document.createElement("table");
  table.className = "trace-marker-table";
  const tableHead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const headers = ["Marker", "Time", "Annotate", ...traceSeries.map((series) => traceHeader(traceSeries, series))];
  for (const headingText of headers) {
    const header = document.createElement("th");
    header.textContent = middleEllipsis(headingText);
    header.title = headingText;
    headerRow.appendChild(header);
  }
  tableHead.appendChild(headerRow);

  const tableBody = document.createElement("tbody");
  for (const marker of pinnedTraceMarkers) {
    const row = document.createElement("tr");
    const markerCell = document.createElement("th");
    markerCell.scope = "row";
    markerCell.textContent = `(${marker.id})`;
    const timeCell = document.createElement("td");
    timeCell.textContent = new Date(marker.pinnedAt).toLocaleString();
    const annotateCell = document.createElement("td");
    const annotateButton = document.createElement("button");
    annotateButton.className = "trace-copy-button";
    annotateButton.type = "button";
    annotateButton.textContent = "Add";
    annotateButton.title = `Add annotation for marker (${marker.id})`;
    annotateButton.addEventListener("click", () => addMarkerAnnotation(marker));
    annotateCell.appendChild(annotateButton);
    row.append(markerCell, timeCell, annotateCell);

    const valuesByTrace = new Map(marker.values.map((series) => [series.traceIndex, series]));
    for (const series of traceSeries) {
      const valueCell = document.createElement("td");
      const value = valuesByTrace.get(series.traceIndex);
      valueCell.textContent = value ? Number(value.point.value).toFixed(3) : "";
      row.appendChild(valueCell);
    }
    tableBody.appendChild(row);
  }
  table.append(tableHead, tableBody);
  markerPanel.appendChild(table);
}

export function pinnedTraceMarkdown(pinnedTraceMarkers, traceSeries) {
  const headers = ["Marker", "Time", ...traceSeries.map((series) => traceHeader(traceSeries, series))];
  const rows = pinnedTraceMarkers.map((marker) => {
    const valuesByTrace = new Map(marker.values.map((series) => [series.traceIndex, series]));
    return [`(${marker.id})`, new Date(marker.pinnedAt).toLocaleString(), ...traceSeries.map((series) => {
      const value = valuesByTrace.get(series.traceIndex);
      return value ? Number(value.point.value).toFixed(3) : "";
    })];
  });
  const escapeMarkdownCell = (value) => String(value).replace(/\|/g, "\\|");
  return [`| ${headers.map(escapeMarkdownCell).join(" | ")} |`, `| ${headers.map(() => "---").join(" | ")} |`, ...rows.map((row) => `| ${row.map(escapeMarkdownCell).join(" | ")} |`)].join("\n");
}

export function annotationText(marker) {
  const text = window.prompt(`Annotation for marker (${marker.id})`);
  return text ? text.trim() : "";
}

export function traceOverlayPlugin({ pinnedTraceMarkers, traceAnnotations }) {
  return {
    hooks: {
      draw: [
        (u) => {
          const colors = traceColors();
          const ctx = u.ctx;
          ctx.save();
          ctx.strokeStyle = colors.trace;
          ctx.fillStyle = colors.text;
          ctx.setLineDash([2, 4]);
          ctx.font = "12px sans-serif";
          for (const marker of pinnedTraceMarkers) {
            const x = u.valToPos(Date.parse(marker.pinnedAt) / 1000, "x", true);
            ctx.beginPath();
            ctx.moveTo(x, u.bbox.top);
            ctx.lineTo(x, u.bbox.top + u.bbox.height);
            ctx.stroke();
            ctx.fillText(`(${marker.id})`, x + 4, u.bbox.top + 14);
          }
          ctx.setLineDash([]);
          for (const annotation of traceAnnotations) {
            const x = u.valToPos(Date.parse(annotation.pinnedAt) / 1000, "x", true);
            ctx.fillText(`(${annotation.markerId}) ${annotation.text}`, x + 4, u.bbox.top + 32);
          }
          ctx.restore();
        },
      ],
    },
  };
}

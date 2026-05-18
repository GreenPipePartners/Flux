export const TRACE_PALETTE = ["#32d583", "#60a5fa", "#f97316", "#c084fc", "#f43f5e", "#facc15", "#2dd4bf", "#fb7185"];

export function traceColors() {
  const style = getComputedStyle(document.documentElement);
  return {
    grid: "rgba(255,255,255,0.12)",
    text: style.getPropertyValue("--text").trim(),
    trace: style.getPropertyValue("--green").trim(),
  };
}

export function createTracePlot({ element, data, series, plugins = [] }) {
  const colors = traceColors();
  const axisGroups = traceAxisGroups(series);
  return new window.uPlot({
    width: element.clientWidth,
    height: 360,
    cursor: { drag: { x: true, y: false } },
    scales: traceScales(axisGroups),
    axes: [
      { stroke: colors.text, grid: { stroke: colors.grid }, font: "11px sans-serif", size: 38, gap: 4, ticks: { size: 4 } },
      ...axisGroups.map((axis) => ({
        scale: axis.key,
        stroke: colors.text,
        grid: { show: axis.key === axisGroups[0].key, stroke: colors.grid },
        label: `${axis.label}${axis.unit && axis.unit !== "mixed" ? ` (${axis.unit})` : ""}`,
        font: "10px sans-serif",
        labelFont: "11px sans-serif",
        size: 42,
        gap: 4,
        ticks: { size: 4 },
        side: axis.side,
      })),
    ],
    series: [
      { label: "Read At" },
      ...series.map((trace, index) => {
        const color = TRACE_PALETTE[index % TRACE_PALETTE.length];
        return {
          label: trace.name,
          scale: trace.axisKey || "process",
          stroke: color,
          points: { show: false, stroke: color, fill: color, size: 7 },
          width: 2,
        };
      }),
    ],
    plugins,
  }, data, element);
}

export function setTracePlotPayload(plot, payload, data, series) {
  while (plot.series.length > 1) plot.delSeries(1);
  for (const [index, trace] of series.entries()) {
    const color = TRACE_PALETTE[index % TRACE_PALETTE.length];
    plot.addSeries({
      label: trace.name,
      scale: trace.axisKey || "process",
      stroke: color,
      points: { show: false, stroke: color, fill: color, size: 7 },
      width: 2,
    });
  }
  plot.setData(data);
}

function traceAxisGroups(series) {
  const byKey = new Map();
  for (const trace of series) {
    for (const axis of trace.axisGroups || []) {
      byKey.set(axis.key, axis);
    }
  }
  if (!byKey.size) {
    byKey.set("process", { key: "process", label: "Process", unit: "mixed", range: [0, 650], side: 3 });
  }
  return Array.from(byKey.values()).filter((axis) => series.some((trace) => (trace.axisKey || "process") === axis.key));
}

function traceScales(axisGroups) {
  const scales = { x: { time: true } };
  for (const axis of axisGroups) {
    scales[axis.key] = Array.isArray(axis.range) && axis.range.length === 2 ? { range: () => axis.range } : {};
  }
  return scales;
}

export function resizeTracePlot(plot, element) {
  plot.setSize({ width: element.clientWidth, height: 360 });
}


export function hoverBoldLinePlugin({ getTraceSeries }) {
  let activeSeriesIndex = null;
  let activeAxisIndex = null;
  const hoverThresholdPx = 14;
  return {
    hooks: {
      setCursor: [
        (u) => {
          const dataIndex = u.cursor.idx;
          if (dataIndex === null || dataIndex === undefined || u.cursor.top === null || u.cursor.top === undefined) {
          setSeriesWidth(u, activeSeriesIndex, 2);
          setAxisFocus(u, null);
          activeSeriesIndex = null;
          activeAxisIndex = null;
            return;
          }
          const nextSeriesIndex = nearestSeriesIndexAtCursor(u, getTraceSeries(), dataIndex, hoverThresholdPx);
          const nextAxisIndex = axisIndexForSeries(u, nextSeriesIndex);
          if (nextSeriesIndex === activeSeriesIndex) return;
          setSeriesWidth(u, activeSeriesIndex, 2);
          setSeriesWidth(u, nextSeriesIndex, 5);
          setAxisFocus(u, nextAxisIndex);
          activeSeriesIndex = nextSeriesIndex;
          activeAxisIndex = nextAxisIndex;
        },
      ],
    },
  };
}


function nearestSeriesIndexAtCursor(u, traceSeries, dataIndex, hoverThresholdPx) {
  if (!traceSeries.length) return null;
  const cursorTop = u.cursor.top;
  let nearest = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < traceSeries.length; index += 1) {
    const value = u.data[index + 1]?.[dataIndex];
    if (value === null || value === undefined) continue;
    const scaleKey = traceSeries[index].axisKey || "process";
    const y = u.valToPos(value, scaleKey, false);
    const distance = Math.abs(y - cursorTop);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = index + 1;
    }
  }
  return nearestDistance <= hoverThresholdPx ? nearest : null;
}


function setSeriesWidth(u, seriesIndex, width) {
  if (!seriesIndex || !u.series[seriesIndex]) return;
  u.series[seriesIndex].width = width;
  u.redraw();
}


function axisIndexForSeries(u, seriesIndex) {
  if (!seriesIndex || !u.series[seriesIndex]) return null;
  const scaleKey = u.series[seriesIndex].scale;
  return u.axes.findIndex((axis, index) => index > 0 && axis.scale === scaleKey);
}


function setAxisFocus(u, activeAxisIndex) {
  const colors = traceColors();
  for (let index = 1; index < u.axes.length; index += 1) {
    const axisColor = !activeAxisIndex || index === activeAxisIndex ? colors.text : "rgba(148,163,184,0.45)";
    const gridColor = !activeAxisIndex || index === activeAxisIndex ? colors.grid : "rgba(148,163,184,0.08)";
    u.axes[index].stroke = () => axisColor;
    u.axes[index].grid = { ...u.axes[index].grid, stroke: () => gridColor };
  }
  u.redraw();
}

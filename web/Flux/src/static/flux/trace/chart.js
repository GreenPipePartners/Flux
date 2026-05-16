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
  return new window.uPlot({
    width: element.clientWidth,
    height: 360,
    cursor: { drag: { x: false, y: false } },
    scales: { x: { time: true } },
    axes: [
      { stroke: colors.text, grid: { stroke: colors.grid } },
      { stroke: colors.text, grid: { stroke: colors.grid }, label: "Value" },
    ],
    series: [
      { label: "Read At" },
      ...series.map((trace, index) => {
        const color = TRACE_PALETTE[index % TRACE_PALETTE.length];
        return { label: trace.name, stroke: color, points: { show: true, stroke: color, fill: color, size: 7 }, width: 2 };
      }),
    ],
    plugins,
  }, data, element);
}

export function resizeTracePlot(plot, element) {
  plot.setSize({ width: element.clientWidth, height: 360 });
}

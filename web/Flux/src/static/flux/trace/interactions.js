export function closestTraceIndex(plot, clientX) {
  const xValues = plot.data[0];
  if (!xValues.length) return null;
  const rect = plot.over.getBoundingClientRect();
  const xPosition = clientX - rect.left;
  if (xPosition < 0 || xPosition > rect.width) return null;
  const xMin = plot.scales.x.min;
  const xMax = plot.scales.x.max;
  if (!Number.isFinite(xMin) || !Number.isFinite(xMax) || xMax <= xMin) return null;
  const clickedValue = xMin + (xPosition / rect.width) * (xMax - xMin);

  let closestIndex = 0;
  let closestDistance = Math.abs(xValues[0] - clickedValue);
  for (let index = 1; index < xValues.length; index += 1) {
    const distance = Math.abs(xValues[index] - clickedValue);
    if (distance < closestDistance) {
      closestDistance = distance;
      closestIndex = index;
    }
  }
  return closestIndex;
}

export function isInsideTraceChart(element, clientX, clientY) {
  const rect = element.getBoundingClientRect();
  return clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom;
}

export function wheelPanZoomPlugin(factor = 0.75) {
  return {
    hooks: {
      ready: [(u) => {
        u.over.addEventListener("wheel", (event) => {
          event.preventDefault();
          const min = u.scales.x.min;
          const max = u.scales.x.max;
          const range = max - min;
          if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
            const secondsPerPixel = range / u.bbox.width;
            const shift = event.deltaX * secondsPerPixel;
            u.setScale("x", { min: min + shift, max: max + shift });
            return;
          }
          const { left, width } = u.over.getBoundingClientRect();
          const cursorRatio = (event.clientX - left) / width;
          const nextRange = event.deltaY < 0 ? range * factor : range / factor;
          const anchor = min + range * cursorRatio;
          u.setScale("x", { min: anchor - nextRange * cursorRatio, max: anchor + nextRange * (1 - cursorRatio) });
        }, { passive: false });
      }],
    },
  };
}

export function dragPanPlugin(onDragState = () => {}) {
  let startX = null;
  let startMin = null;
  let startMax = null;
  return {
    hooks: {
      ready: [(u) => {
        u.over.addEventListener("mousedown", (event) => {
          if (!event.shiftKey) return;
          startX = event.clientX;
          startMin = u.scales.x.min;
          startMax = u.scales.x.max;
        });
        window.addEventListener("mousemove", (event) => {
          if (startX === null) return;
          if (!event.shiftKey) return;
          const delta = event.clientX - startX;
          if (Math.abs(delta) > 3) onDragState(true);
          const range = startMax - startMin;
          const secondsPerPixel = range / u.bbox.width;
          u.setScale("x", { min: startMin - delta * secondsPerPixel, max: startMax - delta * secondsPerPixel });
        });
        window.addEventListener("mouseup", () => {
          startX = null;
          window.setTimeout(() => onDragState(false), 100);
        });
      }],
    },
  };
}

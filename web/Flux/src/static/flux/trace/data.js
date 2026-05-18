export function traceSeriesFromPayload(payload) {
  const series = payload.series.map((item, traceIndex) => ({ ...item, axisGroups: payload.axisGroups || [], traceIndex }));
  series.sharedX = payload.x || null;
  return series;
}

export function alignTracePayload(seriesList) {
  if (seriesList.sharedX) {
    return { times: seriesList.sharedX, data: [seriesList.sharedX, ...seriesList.map((series) => series.y)] };
  }
  const seen = new Set();
  const times = [];
  for (const series of seriesList) {
    for (const time of series.x) {
      if (!seen.has(time)) {
        seen.add(time);
        times.push(time);
      }
    }
  }
  times.sort();

  const timeIndex = new Map();
  const xValues = new Array(times.length);
  for (let index = 0; index < times.length; index += 1) {
    timeIndex.set(times[index], index);
    xValues[index] = Date.parse(times[index]) / 1000;
  }

  const data = [xValues];
  for (const series of seriesList) {
    const values = new Array(times.length).fill(null);
    for (let index = 0; index < series.x.length; index += 1) {
      values[timeIndex.get(series.x[index])] = Number(series.y[index]);
    }
    data.push(values);
  }
  return { times, data };
}

export function nearestTraceValues(traceSeries, aligned, index) {
  const values = [];
  for (let seriesIndex = 0; seriesIndex < traceSeries.length; seriesIndex += 1) {
    const value = aligned.data[seriesIndex + 1][index];
    if (!Number.isFinite(Number(value))) continue;
    const series = traceSeries[seriesIndex];
    values.push({
      name: series.name,
      fullPath: series.fullPath,
      traceIndex: series.traceIndex,
      point: { time: aligned.data[0][index] * 1000, value: Number(value) },
    });
  }
  return values;
}

export function newestTraceTime(aligned) {
  const xValues = aligned.data[0];
  return xValues.length ? xValues[xValues.length - 1] * 1000 : null;
}

export function mergeLiveSeries(liveTraceData, seriesPayload) {
  for (const incoming of seriesPayload.series) {
    let existing = liveTraceData.find((series) => series.tagId === incoming.tagId);
    if (!existing) {
      existing = { x: [], y: [], name: incoming.name, fullPath: incoming.fullPath, tagId: incoming.tagId };
      liveTraceData.push(existing);
    }
    const existingTimes = new Set(existing.x);
    for (let index = 0; index < incoming.x.length; index += 1) {
      const time = incoming.x[index];
      if (existingTimes.has(time)) continue;
      existingTimes.add(time);
      existing.x.push(time);
      existing.y.push(incoming.y[index]);
    }
  }
}

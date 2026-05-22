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
  if (liveTraceData.sharedX) {
    mergeSharedXSeries(liveTraceData, seriesPayload);
    return;
  }
  const incomingSharedX = seriesPayload.x || [];
  for (const incoming of seriesPayload.series) {
    let existing = liveTraceData.find((series) => series.tagId === incoming.tagId);
    if (!existing) {
      existing = { x: [], y: [], name: incoming.name, fullPath: incoming.fullPath, tagId: incoming.tagId, axisKey: incoming.axisKey, unit: incoming.unit };
      liveTraceData.push(existing);
    }
    const incomingTimes = incoming.x.length ? incoming.x : incomingSharedX;
    const existingTimes = new Set(existing.x);
    for (let index = 0; index < incomingTimes.length; index += 1) {
      const time = incomingTimes[index];
      if (existingTimes.has(time)) continue;
      existingTimes.add(time);
      existing.x.push(time);
      existing.y.push(incoming.y[index]);
    }
  }
}

function mergeSharedXSeries(liveTraceData, seriesPayload) {
  const incomingX = seriesPayload.x || [];
  const existingTimes = new Set(liveTraceData.sharedX);
  const appendedIndexes = [];
  for (let index = 0; index < incomingX.length; index += 1) {
    const time = incomingX[index];
    if (existingTimes.has(time)) continue;
    existingTimes.add(time);
    liveTraceData.sharedX.push(time);
    appendedIndexes.push([index, liveTraceData.sharedX.length - 1]);
  }
  if (!appendedIndexes.length) return;

  for (const series of liveTraceData) {
    for (let index = 0; index < appendedIndexes.length; index += 1) series.y.push(null);
  }
  for (const incoming of seriesPayload.series) {
    let existing = liveTraceData.find((series) => series.tagId === incoming.tagId);
    if (!existing) {
      existing = { x: [], y: new Array(liveTraceData.sharedX.length).fill(null), name: incoming.name, fullPath: incoming.fullPath, tagId: incoming.tagId, axisKey: incoming.axisKey, unit: incoming.unit };
      liveTraceData.push(existing);
    }
    for (const [incomingIndex, sharedIndex] of appendedIndexes) {
      existing.y[sharedIndex] = incoming.y[incomingIndex];
    }
  }
}

import { escapeHtml, time } from './presentation.js';

export const temperatureChart = (history = []) => {
  const points = history.filter(p => Number.isFinite(Number(p.temperature))).slice(-40);
  if (!points.length) return '<div class="empty chart-empty">Waiting for telemetry. Start the simulation to see readings.</div>';
  const width = 680, height = 212, left = 38, right = 15, top = 18, bottom = 30;
  const min = Math.floor(Math.min(20, ...points.map(p => Number(p.temperature))) / 10) * 10;
  const max = Math.ceil(Math.max(60, ...points.map(p => Number(p.temperature))) / 10) * 10;
  const x = (index) => left + (points.length === 1 ? 0.5 : index / (points.length - 1)) * (width-left-right);
  const y = (value) => top + (1 - (value - min) / (max - min)) * (height-top-bottom);
  const line = points.map((p,i) => `${i ? 'L' : 'M'}${x(i).toFixed(2)},${y(Number(p.temperature)).toFixed(2)}`).join(' ');
  const grid = Array.from({length:5}, (_,i) => {
    const value = min + (max-min) * i / 4;
    return `<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="#e9edf2" stroke-dasharray="3 4"/><text x="24" y="${y(value)+4}" text-anchor="end">${Math.round(value)}°</text>`;
  }).join('');
  const last = points.at(-1);
  const labels = [...new Set([0, Math.floor((points.length-1)/2), points.length-1])].map(i => `<text x="${x(i)}" y="${height-6}" text-anchor="${i === 0 ? 'start' : i === points.length-1 ? 'end' : 'middle'}">${escapeHtml(time(points[i].at))}</text>`).join('');
  return `<svg class="telemetry-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Temperature history with ${points.length} readings. Latest ${Number(last.temperature).toFixed(1)} degrees Celsius."><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#4f7ffa" stop-opacity=".18"/><stop offset="100%" stop-color="#4f7ffa" stop-opacity=".01"/></linearGradient></defs>${grid}<path d="${line} L${x(points.length-1)},${height-bottom} L${x(0)},${height-bottom} Z" fill="url(#chart-fill)"/><path d="${line}" stroke="#3c70ee" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${x(points.length-1)}" cy="${y(Number(last.temperature))}" r="4.5" fill="#3c70ee" stroke="#fff" stroke-width="2"/>${labels}</svg>`;
};

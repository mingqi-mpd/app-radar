'use strict';
const $ = id => document.getElementById(id);
const categories = ['Games', 'Finance', 'Shopping', 'Casino', 'Sports', 'Social Networking', 'Utilities', 'Entertainment'];
let data = null, days = [], visible = [];

function toast(text) { $('toast').textContent = text; $('toast').hidden = false; setTimeout(() => $('toast').hidden = true, 3500); }
function shortDate(iso) { return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' }).format(new Date(iso + 'T00:00:00Z')); }
function hasList(d) { return d.complete && !d.is_baseline; }

function selectLeads(d, category, query) {
  if (!hasList(d)) return [];
  const q = query.trim().toLowerCase();
  return d.leads
    .map(a => ({ ...a, _date: d.date, charts: a.charts.filter(c => d.coverage[c.category]?.ready && (!category || c.category === category)) }))
    .filter(a => a.charts.length && `${a.name} ${a.developer}`.toLowerCase().includes(q));
}

function selectedDays() { const v = $('day').value; return v === 'all' ? days : days.filter(d => d.date === v); }

function formatRatings(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  if (n < 1000) return String(n);
  const units = [[1e9, 'B'], [1e6, 'M'], [1e3, 'K']];
  for (let i = 0; i < units.length; i++) {
    const [u, s] = units[i];
    if (n < u) continue;
    const v = n / u, d = v < 10 ? 1 : 0, r = Math.round(v * 10 ** d) / 10 ** d;
    if (r >= 1000 && i > 0) { const [u2, s2] = units[i - 1]; return (Math.round(n / u2 * 10) / 10).toString() + s2; }
    return r.toString() + s;
  }
  return String(n);
}

function cell(text) { const t = document.createElement('td'); t.textContent = text; return t; }

function dayLabel(d, isLatest) {
  const when = shortDate(d.date) + (isLatest ? ' (latest)' : '');
  if (!d.complete) return `${when} · incomplete`;
  if (d.is_baseline) return `${when} · baseline`;
  const n = selectLeads(d, '', '').length;
  return `${when} · ${n} new`;
}

function renderNotice() {
  const v = $('day').value, d = data;
  if (v === 'all') {
    const total = days.reduce((sum, x) => sum + selectLeads(x, '', '').length, 0);
    $('notice').textContent = `Showing ${total} new entrant(s) from the last ${days.length} recorded day(s). Each app is listed once, on the day it first qualified.`;
    return;
  }
  if (v !== d.date) {
    const past = days.find(x => x.date === v);
    $('notice').textContent = !past.complete ? `The ${shortDate(v)} collection was incomplete, so no list was published that day.`
      : past.is_baseline ? `${shortDate(v)} was the baseline day; no list was published.`
      : `Showing the list published on ${shortDate(v)}. Ratings are as of that day.`;
    return;
  }
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  $('notice').textContent = today !== d.date ? `Showing the ${d.date} snapshot. Today's update is not available.`
    : !d.complete ? 'Collection failed or is incomplete. No daily list is available.'
    : d.is_baseline ? 'Baseline saved. Tomorrow’s list will compare against today; earlier unrecorded days count as no appearance.'
    : `Compared with ${d.history_days} recorded day(s) in the previous 30-day window; ${d.unrecorded_history_days} earlier day(s) count as no appearance.`;
  if (d.incomplete_history_dates.length) $('notice').textContent += ` ${d.incomplete_history_dates.length} recorded day(s) were incomplete; successfully observed App IDs still count.`;
}

function render() {
  if (!data) return;
  const cat = $('category').value, q = $('search').value, all = $('day').value === 'all';
  const chosen = selectedDays();
  visible = chosen.flatMap(d => selectLeads(d, cat, q));
  const single = all ? null : chosen[0];
  const stat = single || data;
  $('rows').textContent = `${categories.filter(c => stat.coverage[c]?.current_available).length} / 8`;
  $('new').textContent = all ? days.reduce((s, x) => s + selectLeads(x, '', '').length, 0) : hasList(single) ? selectLeads(single, '', '').length : '—';
  $('new-label').textContent = all ? `Qualified new apps (${days.length} days)` : 'Qualified new apps';
  $('count').textContent = `${visible.length} matching ${visible.length === 1 ? 'app' : 'apps'} · Deduplicated across all 8 categories`;
  const body = $('body'); body.replaceChildren();
  for (const a of visible) {
    const tr = document.createElement('tr');
    tr.append(cell(a.charts.map(c => '#' + c.rank).join(' / ')));
    const name = document.createElement('td'), strong = document.createElement('strong'), dev = document.createElement('div');
    strong.textContent = a.name; dev.className = 'developer'; dev.textContent = a.developer; name.append(strong, dev);
    tr.append(name, cell(a.charts.map(c => c.category).join(' / ')));
    const status = document.createElement('td'), badge = document.createElement('span');
    badge.className = 'badge fresh'; badge.textContent = all ? `New · ${shortDate(a._date)}` : 'New entrant';
    status.append(badge); tr.append(status);
    const link = document.createElement('a');
    link.href = `https://apps.apple.com/us/app/id${encodeURIComponent(a.id)}`; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.textContent = 'App Store ↗'; link.setAttribute('aria-label', `View ${a.name} on the App Store`);
    const td = document.createElement('td'); td.append(link); tr.append(td);
    const rc = cell(formatRatings(a.rating_count)); rc.className = 'num';
    if (typeof a.rating_count === 'number') rc.title = a.rating_count.toLocaleString('en-US') + ' ratings';
    tr.append(rc); body.append(tr);
  }
  $('empty').hidden = visible.length > 0; $('export').disabled = visible.length === 0;
  if (!visible.length) {
    const empty = $('empty'), h = empty.querySelector('h2'), p = empty.querySelector('p');
    if (q.trim() || cat) { h.textContent = 'No matching apps'; p.textContent = 'Try another app name, developer, category, or date.'; }
    else if (all) { h.textContent = 'No new entrants in the last 7 days'; p.textContent = 'No complete daily list in this period had qualifying apps.'; }
    else if (!single.complete) { h.textContent = 'Collection incomplete'; p.textContent = 'All eight charts must be collected before publishing a daily list. Missing data is not a zero-result day.'; }
    else if (single.is_baseline) { h.textContent = 'Baseline saved'; p.textContent = 'This day’s apps formed the starting list. The next day, apps absent from these charts could qualify.'; }
    else { h.textContent = 'No 30-day entrants on this day'; p.textContent = 'Every app appeared in at least one monitored category during the previous 30 days.'; }
  }
  renderNotice();
}

$('day').onchange = render; $('category').onchange = render; $('search').oninput = render;
$('share').onclick = async () => { try { await navigator.clipboard.writeText(location.href); toast('Link copied'); } catch { toast('Copy the URL from your browser’s address bar to share'); } };
$('export').onclick = () => {
  const safe = v => '"' + String(v).replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""') + '"';
  const rows = [['List date', 'App', 'Developer', 'Qualifying categories and ranks', 'App Store', 'US ratings'],
    ...visible.map(a => [a._date, a.name, a.developer, a.charts.map(c => `${c.category} #${c.rank}`).join('; '), `https://apps.apple.com/us/app/id${a.id}`, typeof a.rating_count === 'number' ? a.rating_count : ''])];
  const blob = new Blob(['﻿' + rows.map(r => r.map(safe).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = `app-radar-new-entrants-${$('day').value === 'all' ? 'last-7-days-' + data.date : $('day').value}.csv`;
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};

fetch('data.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw Error('load'); return r.json(); }).then(d => {
  data = d;
  days = (Array.isArray(d.recent_days) && d.recent_days.length ? d.recent_days : [d]).slice().sort((x, y) => y.date.localeCompare(x.date));
  for (const category of categories) { const opt = document.createElement('option'); opt.value = category; opt.textContent = category; $('category').append(opt); }
  days.forEach((x, i) => { const opt = document.createElement('option'); opt.value = x.date; opt.textContent = dayLabel(x, i === 0 && x.date === d.date); $('day').append(opt); });
  const allOpt = document.createElement('option'); allOpt.value = 'all';
  allOpt.textContent = `All last ${days.length} day(s) · ${days.reduce((s, x) => s + selectLeads(x, '', '').length, 0)} new`;
  $('day').append(allOpt);
  $('day').value = d.date;
  $('date').textContent = `Snapshot: ${d.date} · Europe/Rome`;
  $('tracking-window').firstChild.textContent = d.window_days;
  render();
}).catch(() => {
  $('notice').textContent = 'Unable to load the snapshot. Please refresh to try again.'; $('date').textContent = 'Snapshot unavailable';
  $('empty').hidden = false; $('empty').querySelector('h2').textContent = 'Data temporarily unavailable'; $('empty').querySelector('p').textContent = 'Please try again later.';
});

if (document.modelContext?.registerTool) {
  const lifecycle = new AbortController();
  try {
    Promise.resolve(document.modelContext.registerTool({
      name: 'filter_app_charts', title: 'Filter new chart entrants',
      description: 'Filter confirmed new entrants, update the page, and return the match count and first ten results.',
      inputSchema: { type: 'object', properties: { category: { type: 'string', enum: ['', ...categories] }, query: { type: 'string' } }, required: ['category', 'query'], additionalProperties: false },
      annotations: { readOnlyHint: false, untrustedContentHint: true },
      execute(input) {
        if (!data) throw Error('Snapshot not loaded');
        if (!input || !['', ...categories].includes(input.category) || typeof input.query !== 'string') throw Error('Invalid filters');
        $('category').value = input.category; $('search').value = input.query; render();
        return { date: $('day').value, count: visible.length, results: visible.slice(0, 10) };
      }
    }, { signal: lifecycle.signal })).catch(() => {});
  } catch {}
  window.addEventListener('pagehide', () => lifecycle.abort(), { once: true });
}

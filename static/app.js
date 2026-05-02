const API_BASE = '';

async function fetchJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
}

function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString('en-GB');
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = { startDate: null, endDate: null };

const FIGURE_CATALOG = [
    {key: 'fig_best_models_combined', label: 'Best models — predictions (paper Fig. 4)'},
    {key: 'LineaA_fig3_ratio_NP',     label: 'N:P molar ratio (paper Fig. 2)'},
    {key: 'LineaB_fig3_relacion_CQ',  label: 'C-Q relationships (paper Fig. 3)'},
    {key: 'LineaA_fig1_contribucion', label: 'Cumulative load ranking (supplementary)'},
];

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------
async function loadStatus() {
    const banner = document.getElementById('status-banner');
    try {
        const s = await fetchJSON(`${API_BASE}/api/status`);
        const ok = s.master_json_present && s.excel_present;
        banner.className = 'status-banner ' + (ok ? 'ok' : s.excel_present ? 'warn' : 'err');
        let metaHtml = '';
        if (s.scraper_meta && s.scraper_meta.remote_filename) {
            metaHtml = `|
            <strong>Portal file:</strong> ${s.scraper_meta.remote_filename}
            |
            <strong>Downloaded:</strong> ${fmtDate(s.scraper_meta.downloaded_at)}`;
        }
        banner.innerHTML = `
            <strong>Status:</strong> ${ok ? 'All set' : s.excel_present ? 'Pipeline pending' : 'Excel not found'}
            |
            <strong>Last run:</strong> ${fmtDate(s.last_pipeline)}
            |
            <strong>Errors:</strong> ${s.errors_count ?? 0}
            ${metaHtml}
        `;
        document.getElementById('last-update').textContent = fmtDate(s.time);
    } catch (e) {
        banner.className = 'status-banner err';
        banner.textContent = 'Unable to contact API.';
    }
}

// ---------------------------------------------------------------------------
// Latest records
// ---------------------------------------------------------------------------
async function loadLatestRecords() {
    const el = document.getElementById('latest-records');
    try {
        const data = await fetchJSON(`${API_BASE}/api/latest-records`);
        if (!data.records || !data.records.length) {
            el.textContent = 'No recent records available.';
            return;
        }
        const rows = data.records.map(r => `
            <tr>
                <td>${r.date}</td>
                <td>${r.no3 !== null ? r.no3.toFixed(2) : '—'}</td>
                <td>${r.po4 !== null ? r.po4.toFixed(3) : '—'}</td>
                <td>${r.caudal !== null ? r.caudal.toFixed(2) : '—'}</td>
            </tr>
        `).join('');
        el.innerHTML = `
            <div class="table-wrap">
            <table>
                <thead><tr><th>Date</th><th>NO₃ (mg/l)</th><th>PO₄ (mg/l)</th><th>Q (m³/s)</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
            </div>
        `;
    } catch (e) {
        el.textContent = 'Error loading latest records.';
    }
}

// ---------------------------------------------------------------------------
// Section 01 — Source Apportionment + N:P
// ---------------------------------------------------------------------------
async function loadSection01() {
    const params = new URLSearchParams();
    if (state.startDate) params.set('start_date', state.startDate);
    if (state.endDate) params.set('end_date', state.endDate);
    const data = await fetchJSON(`${API_BASE}/api/section/01?${params}`);

    // Metrics
    const loadMetrics = document.getElementById('sec01-load-metrics');
    const no3Top = data.tables.totales_no3_top5[0];
    const po4Top = data.tables.totales_po4_top5[0];
    loadMetrics.innerHTML = `
        <div class="metric"><div class="value">${no3Top ? no3Top.total_tonnes : '—'}</div><div class="label">Top NO₃ (t) — Pto.${no3Top ? no3Top.pto : ''}</div></div>
        <div class="metric"><div class="value">${po4Top ? po4Top.total_tonnes : '—'}</div><div class="label">Top PO₄ (t) — Pto.${po4Top ? po4Top.pto : ''}</div></div>
    `;

    const npMetrics = document.getElementById('sec01-np-metrics');
    const pt2 = data.tables.ratio_np_summary.find(r => r.pto === '2');
    npMetrics.innerHTML = `
        ${pt2 ? `<div class="metric"><div class="value">${pt2.mediana}</div><div class="label">N:P median Pto.2</div></div>
        <div class="metric"><div class="value">${pt2.pct_P_limitante}%</div><div class="label">% P limiting</div></div>` : ''}
    `;

    // Plotly charts
    const lr = data.plots.load_ranking;
    const nBars = Math.max(lr.no3.y.length, lr.po4.y.length);
    const chartHeight = Math.max(420, nBars * 38);
    const maxNO3 = Math.max(...lr.no3.x, 1);
    const maxPO4 = Math.max(...lr.po4.x, 1);
    const loadLayout = {
        grid: {rows: 1, columns: 2, pattern: 'independent'},
        width: 900,
        height: chartHeight,
        autosize: false,
        margin: {l: 160, r: 60, t: 40, b: 40},
        showlegend: false,
        xaxis: {range: [0, maxNO3 * 1.2]},
        xaxis2: {range: [0, maxPO4 * 1.2]},
    };
    const loadData = [
        {
            type: 'bar', x: lr.no3.x, y: lr.no3.y,
            orientation: 'h', marker: {color: lr.no3.colors},
            text: lr.no3.pct.map(p => `${p.toFixed(1)}%`), textposition: 'auto',
            name: 'NO₃', xaxis: 'x', yaxis: 'y',
        },
        {
            type: 'bar', x: lr.po4.x, y: lr.po4.y,
            orientation: 'h', marker: {color: lr.po4.colors},
            text: lr.po4.pct.map(p => `${p.toFixed(1)}%`), textposition: 'auto',
            name: 'PO₄', xaxis: 'x2', yaxis: 'y2',
        },
    ];
    Plotly.newPlot('plot-load-ranking', loadData, loadLayout, {responsive: false});

    // N:P boxplot
    const bp = data.plots.np_boxplot;
    const boxData = bp.data.map((vals, i) => ({
        type: 'box', y: vals, name: bp.labels[i],
        boxpoints: 'outliers', marker: {color: '#90caf9'},
    }));
    boxData.push({type: 'scatter', mode: 'lines', x: [0, bp.labels.length+1],
        y: [bp.redfield, bp.redfield], line: {color: 'red', dash: 'dash'},
        name: `Redfield = ${bp.redfield}`, showlegend: true});
    const boxLayout = {height: 350, margin: {l: 50, r: 20, t: 30, b: 80},
        yaxis: {title: 'Molar N:P ratio'}, xaxis: {tickangle: 30},
        showlegend: true, legend: {y: 1.1, orientation: 'h'}};
    Plotly.newPlot('plot-np-box', boxData, boxLayout, {responsive: true});

    // N:P temporal
    const tp = data.plots.np_temporal;
    if (tp && tp.dates && tp.dates.length) {
        const temporalData = [
            {type: 'scatter', mode: 'lines', name: 'N:P ratio',
                x: tp.dates, y: tp.values,
                line: {color: 'gray', width: 1}, marker: {size: 3, color: 'gray'}},
            {type: 'scatter', mode: 'lines', name: '8-wk moving avg.',
                x: tp.dates, y: tp.smooth,
                line: {color: '#333', width: 2}},
            {type: 'scatter', mode: 'lines', name: 'Redfield = 16',
                x: [tp.dates[0], tp.dates[tp.dates.length-1]], y: [16, 16],
                line: {color: 'red', dash: 'dash', width: 1.5}},
        ];
        const temporalLayout = {height: 300, margin: {l: 50, r: 20, t: 30, b: 40},
            yaxis: {title: 'Molar N:P ratio', range: [0, 1000]},
            xaxis: {title: 'Date'},
            showlegend: true, legend: {y: 1.15, orientation: 'h'},
            title: `Pto.2 Albujón — Median: ${Math.round(tp.mediana)}`};
        Plotly.newPlot('plot-np-temporal', temporalData, temporalLayout, {responsive: true});
    }
}

// ---------------------------------------------------------------------------
// Section 02 — Hydrological response
// ---------------------------------------------------------------------------
async function loadSection02() {
    const params = new URLSearchParams();
    if (state.startDate) params.set('start_date', state.startDate);
    if (state.endDate) params.set('end_date', state.endDate);
    const data = await fetchJSON(`${API_BASE}/api/section/02?${params}`);

    // Metrics
    const metrics = document.getElementById('sec02-metrics');
    const cc = data.tables.crosscorr;
    const cqNo3 = data.tables.cq_analysis.no3;
    const cqPo4 = data.tables.cq_analysis.po4;
    metrics.innerHTML = `
        <div class="metric"><div class="value">${cc.lag_optimo_dias}</div><div class="label">Optimal lag (days)</div></div>
        <div class="metric"><div class="value">${cc.corr_maxima}</div><div class="label">Max correlation</div></div>
        <div class="metric"><div class="value">${cqNo3 ? cqNo3.slope_b : '—'}</div><div class="label">Slope b NO₃</div></div>
        <div class="metric"><div class="value">${cqPo4 ? cqPo4.slope_b : '—'}</div><div class="label">Slope b PO₄</div></div>
    `;

    // Cross-correlation plot
    const ccPlot = data.plots.crosscorr;
    const ccData = [
        {type: 'scatter', mode: 'lines+markers', name: 'SIAM',
            x: ccPlot.lags, y: ccPlot.correlations,
            line: {color: 'green', width: 1.5}, marker: {size: 4, color: 'green'}},
        {type: 'scatter', mode: 'lines', name: `Optimal lag = ${ccPlot.lag_optimo} days`,
            x: [ccPlot.lag_optimo, ccPlot.lag_optimo], y: [Math.min(...ccPlot.correlations), Math.max(...ccPlot.correlations)],
            line: {color: 'red', dash: 'dash', width: 2}},
    ];
    const ccLayout = {height: 300, margin: {l: 50, r: 20, t: 40, b: 40},
        xaxis: {title: 'Lag (days)'}, yaxis: {title: 'Cross-correlation'},
        showlegend: true, legend: {y: 1.15, orientation: 'h'},
        title: `Max corr = ${ccPlot.corr_maxima}`};
    Plotly.newPlot('plot-crosscorr', ccData, ccLayout, {responsive: true});

    // C-Q scatter plots
    const cq = data.plots.cq_scatter;
    const cqData = [];
    const cqLayout = {
        grid: {rows: 1, columns: 2, pattern: 'independent'},
        height: 320, margin: {l: 60, r: 20, t: 50, b: 50},
        showlegend: true, legend: {y: 1.2, orientation: 'h'},
    };
    [['no3', cq.no3, 'NO₃ (mg/l)', '#c62828'],
     ['po4', cq.po4, 'PO₄ (mg/l)', '#2e7d32']].forEach(([key, res, label, color], i) => {
        if (!res) return;
        const xaxis = i === 0 ? 'x' : 'x2';
        const yaxis = i === 0 ? 'y' : 'y2';
        cqData.push({
            type: 'scatter', mode: 'markers', name: 'Observed',
            x: res.scatter.x, y: res.scatter.y,
            marker: {size: 5, color: color, opacity: 0.6},
            xaxis: xaxis, yaxis: yaxis,
        });
        cqData.push({
            type: 'scatter', mode: 'lines', name: `b=${res.slope_b}, R²=${res.r2}`,
            x: res.fit.x, y: res.fit.y,
            line: {color: 'black', width: 2},
            xaxis: xaxis, yaxis: yaxis,
        });
        cqLayout[`xaxis${i>0 ? i+1 : ''}`] = {title: 'Streamflow Q (l/s) [log]', type: 'log'};
        cqLayout[`yaxis${i>0 ? i+1 : ''}`] = {title: `${label} [log]`, type: 'log'};
    });
    Plotly.newPlot('plot-cq', cqData, cqLayout, {responsive: true});
}

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------
async function loadMap() {
    const el = document.getElementById('study-map');
    try {
        const r = await fetch(`${API_BASE}/api/map`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const contentType = r.headers.get('content-type') || '';
        if (contentType.includes('svg')) {
            const svgText = await r.text();
            el.innerHTML = svgText;
            el.classList.remove('loading');
        } else {
            const blob = await r.blob();
            const url = URL.createObjectURL(blob);
            el.innerHTML = `<img src="${url}" alt="Study area map" style="max-width:100%;height:auto;border-radius:8px;" onload="URL.revokeObjectURL(this.src)">`;
            el.classList.remove('loading');
        }
    } catch (e) {
        el.textContent = 'Map not available.';
        el.classList.remove('loading');
    }
}


// ---------------------------------------------------------------------------
// Forecast (03) — static
// ---------------------------------------------------------------------------
async function loadForecast() {
    try {
        const data = await fetchJSON(`${API_BASE}/api/results`);
        renderForecast(data.scripts['03_lstm_gru_forecast']);
    } catch (e) {
        console.error(e);
    }
}

function renderForecast(lstmRes) {
    const el = document.getElementById('forecast-metrics');
    if (!lstmRes || !lstmRes.metrics || !lstmRes.metrics.length) {
        el.textContent = 'Forecast metrics not available.'; return;
    }

    el.innerHTML = `
        <div class="table-wrap">
        <table>
            <thead><tr><th>Model</th><th>MAE</th><th>RMSE</th><th>MAPE (%)</th><th>CVRMSE (%)</th></tr></thead>
            <tbody>
                ${lstmRes.metrics.map(m => `
                    <tr>
                        <td>${m.Model}</td>
                        <td>${typeof m.MAE === 'number' ? m.MAE.toFixed(3) : m.MAE}</td>
                        <td>${typeof m.RMSE === 'number' ? m.RMSE.toFixed(3) : m.RMSE}</td>
                        <td>${typeof m.MAPE === 'number' ? m.MAPE.toFixed(1) : m.MAPE}</td>
                        <td>${typeof m.CVRMSE === 'number' ? m.CVRMSE.toFixed(1) : m.CVRMSE}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Figures — curated gallery with selector
// ---------------------------------------------------------------------------
async function loadFigures() {
    const selectorEl = document.getElementById('figure-selector');
    const figuresEl = document.getElementById('figures');

    try {
        const list = await fetchJSON(`${API_BASE}/api/figures`);
        if (!list.figures || !list.figures.length) {
            figuresEl.textContent = 'No generated figures yet.';
            return;
        }

        // Build selector checkboxes
        const available = new Set(list.figures);
        const checkboxes = FIGURE_CATALOG.map(fig => {
            const exists = list.figures.some(f => f.startsWith(fig.key));
            return `<label class="fig-check" style="${exists ? '' : 'opacity:0.4'}">
                <input type="checkbox" value="${fig.key}" ${exists ? 'checked' : ''} ${exists ? '' : 'disabled'}>
                ${fig.label}
            </label>`;
        }).join('');
        selectorEl.innerHTML = `<div class="fig-selector-grid">${checkboxes}</div>`;

        renderSelectedFigures(list.figures);

        // Wire checkbox changes
        selectorEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => renderSelectedFigures(list.figures));
        });
    } catch (e) {
        figuresEl.textContent = 'Error loading figures.';
    }
}

function renderSelectedFigures(allFigures) {
    const figuresEl = document.getElementById('figures');
    const checked = [...document.querySelectorAll('#figure-selector input[type="checkbox"]:checked')]
        .map(cb => cb.value);

    if (!checked.length) {
        figuresEl.innerHTML = '<p style="color:#666">Select at least one figure above.</p>';
        return;
    }

    const html = checked.map(key => {
        const name = allFigures.find(f => f.startsWith(key));
        if (!name) return '';
        const label = name.replace(/\.(svg|png)$/, '');
        const imgSrc = `${API_BASE}/api/images/${encodeURIComponent(name)}`;
        return `
            <div class="figure-item">
                <img src="${imgSrc}" alt="${name}" loading="lazy" style="max-width:100%;height:auto;border-radius:6px;">
                <div class="caption">${label}</div>
            </div>
        `;
    }).join('');
    figuresEl.innerHTML = `<div class="figure-grid">${html}</div>`;
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------
document.getElementById('btn-refresh').addEventListener('click', async () => {
    const btn = document.getElementById('btn-refresh');
    btn.disabled = true;
    btn.textContent = 'Updating...';
    try {
        const r = await fetch(`${API_BASE}/api/trigger-update`, { method: 'POST' });
        const data = await r.json();
        alert(data.message);
    } catch (e) {
        alert('Error launching update.');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Update now';
    }
});

document.getElementById('btn-apply-range').addEventListener('click', async () => {
    state.startDate = document.getElementById('date-start').value;
    state.endDate = document.getElementById('date-end').value;
    await loadSection01();
    await loadSection02();
});

document.getElementById('btn-reset-range').addEventListener('click', async () => {
    const range = await fetchJSON(`${API_BASE}/api/data-range`);
    state.startDate = range.start;
    state.endDate = range.end;
    document.getElementById('date-start').value = state.startDate;
    document.getElementById('date-end').value = state.endDate;
    await loadSection01();
    await loadSection02();
});

document.getElementById('btn-download-metrics').addEventListener('click', async () => {
    try {
        const r = await fetch(`${API_BASE}/api/download/metrics`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'forecast_metrics.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('Error downloading metrics.');
    }
});

document.getElementById('btn-download-figures').addEventListener('click', async () => {
    const btn = document.getElementById('btn-download-figures');
    btn.disabled = true;
    btn.textContent = 'Preparing ZIP...';
    try {
        const r = await fetch(`${API_BASE}/api/download/figures`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'figures.zip';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('Error downloading figures.');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Download all figures (ZIP)';
    }
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
async function init() {
    await loadStatus();
    const range = await fetchJSON(`${API_BASE}/api/data-range`);
    state.startDate = range.start;
    state.endDate = range.end;
    document.getElementById('date-start').value = state.startDate;
    document.getElementById('date-end').value = state.endDate;

    await loadMap();
    await loadLatestRecords();
    await loadSection01();
    await loadSection02();
    await loadForecast();
    await loadFigures();
}

init();
setInterval(init, 30000);

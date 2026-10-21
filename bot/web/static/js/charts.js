/**
 * RemnaStore Pro - Charts & Reporting Visualizers
 * DRY reusable chart and breakdown generators using Chart.js.
 */

window.chartInstances = window.chartInstances || {};

let chartLoadPromise = null;
function ensureChart() {
  if (typeof Chart !== 'undefined') {
    return Promise.resolve(window.Chart);
  }
  if (!chartLoadPromise) {
    chartLoadPromise = new Promise((resolve, reject) => {
      const existingScript = document.querySelector('script[src*="chart.umd.min.js"]');
      if (existingScript) {
        if (typeof Chart !== 'undefined') return resolve(window.Chart);
        existingScript.addEventListener('load', () => resolve(window.Chart));
        existingScript.addEventListener('error', (e) => { chartLoadPromise = null; reject(e); });
        return;
      }
      const s = document.createElement('script');
      s.src = '/static/js/chart.umd.min.js';
      s.async = true;
      s.onload = () => resolve(window.Chart);
      s.onerror = (e) => {
        chartLoadPromise = null;
        reject(e);
      };
      document.head.appendChild(s);
    });
  }
  return chartLoadPromise;
}

async function renderBarChart(containerId, totals, labels, isMonthly = false) {
  let canvas = document.getElementById(containerId);
  if (!canvas) return;

  if (typeof Chart === 'undefined') {
    try {
      await ensureChart();
    } catch (e) {
      return;
    }
  }
  if (typeof Chart === 'undefined') return;

  // If container is a div instead of a canvas, find or create canvas inside it
  if (canvas.tagName.toLowerCase() !== 'canvas') {
    let innerCanvas = canvas.querySelector('canvas');
    if (!innerCanvas) {
      canvas.innerHTML = '<canvas dir="ltr" class="w-full h-full"></canvas>';
      innerCanvas = canvas.querySelector('canvas');
    }
    canvas = innerCanvas;
  }
  if (canvas && !canvas.getAttribute('dir')) {
    canvas.setAttribute('dir', 'ltr');
  }

  const isLight = document.documentElement.classList.contains('theme-light');
  const tokens = typeof getChartThemeTokens === 'function' ? getChartThemeTokens(isLight) : null;
  const textColor = tokens ? tokens.tick : (isLight ? '#1e293b' : '#94a3b8');
  const gridColor = tokens ? tokens.grid : (isLight ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.06)');
  // Color palette - consistent brand cyan/sky family for all traffic consumption
  const borderColor = tokens ? tokens.accent : (isLight ? '#0369a1' : '#22d3ee');
  const mainColor = isLight ? 'rgba(2, 132, 199, 0.8)' : 'rgba(34, 211, 238, 0.85)';

  // Clean English data & labels
  const cleanData = (totals || []).map(v => {
    const num = parseFloat(toEnglishDigits(v));
    return isNaN(num) ? 0 : num;
  });
  const cleanLabels = (labels || []).map(l => toEnglishDigits(l));

  // Destroy previous instance on this canvas
  const chartKey = canvas.id || containerId;
  if (window.chartInstances[chartKey]) {
    try {
      window.chartInstances[chartKey].destroy();
    } catch (e) {}
    delete window.chartInstances[chartKey];
  }

  const ctx = canvas.getContext('2d');
  window.chartInstances[chartKey] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: cleanLabels,
      datasets: [{
        data: cleanData,
        backgroundColor: mainColor,
        borderColor: borderColor,
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: isMonthly ? 32 : 22,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 600,
        easing: 'easeOutQuart'
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl: true,
          textDirection: 'rtl',
          displayColors: false,
          backgroundColor: tokens?.tooltipBg || (isLight ? '#ffffff' : '#0f172a'),
          titleColor: tokens?.tooltipTitle || (isLight ? '#0f172a' : '#ffffff'),
          borderColor: isLight ? '#e2e8f0' : '#334155',
          borderWidth: 1,
          bodyColor: tokens?.tooltipBody || (isLight ? '#0369a1' : '#22d3ee'),
          titleFont: { family: 'Vazirmatn', size: 11, weight: 'bold' },
          bodyFont: { family: 'monospace', size: 12, weight: 'bold' },
          padding: 8,
          cornerRadius: 8,
          callbacks: {
            title: function(context) {
              const lbl = context[0]?.label || '';
              return isMonthly ? `هفته ${lbl}` : `روز ${lbl}`;
            },
            label: function(context) {
              const val = context.raw != null ? context.raw : 0;
              return `مصرف: ${fmtTraffic(val, { html: false, isolate: true })}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: {
            color: textColor,
            font: { family: 'Vazirmatn', size: 10, weight: isLight ? '600' : '500' }
          }
        },
        y: {
          position: 'left',
          beginAtZero: true,
          suggestedMax: cleanData.some(v => v > 0) ? undefined : 1,
          grid: {
            color: gridColor,
          },
          border: { display: false },
          ticks: {
            color: textColor,
            font: { family: 'monospace', size: 9, weight: isLight ? '600' : '500' },
            callback: function(val) {
              return fmtTraffic(val, { html: false, isolate: true });
            }
          }
        }
      }
    }
  });
}

function renderNodeBreakdown(containerId, nodes, emptyText = 'مصرفی ثبت نشده است.') {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!nodes || nodes.length === 0) {
    container.innerHTML = `
      <div class="col-span-2 text-center py-2 text-slate-400 text-[10px]">
        ${emptyText}
      </div>
    `;
    return;
  }

  container.innerHTML = nodes.map(n => `
    <div dir="ltr" class="bg-transparent p-2 rounded-lg flex items-center justify-between border border-slate-700/40">
      <span class="text-base">${n.flag || '🌐'}</span>
      <span class="font-bold text-slate-100 font-mono num-bidi" dir="ltr">${fmtTraffic(n.total_formatted || '0 GB', { html: false })}</span>
    </div>
  `).join('');
}

async function renderDonutChart(containerId, labels, data, isDevice = false) {
  let canvas = document.getElementById(containerId);
  if (!canvas) return;

  if (typeof Chart === 'undefined') {
    try {
      await ensureChart();
    } catch (e) {
      return;
    }
  }
  if (typeof Chart === 'undefined') return;

  if (canvas.tagName.toLowerCase() !== 'canvas') {
    let innerCanvas = canvas.querySelector('canvas');
    if (!innerCanvas) {
      canvas.innerHTML = '<canvas dir="ltr" class="w-full h-full"></canvas>';
      innerCanvas = canvas.querySelector('canvas');
    }
    canvas = innerCanvas;
  }
  if (canvas && !canvas.getAttribute('dir')) {
    canvas.setAttribute('dir', 'ltr');
  }

  const isLight = document.documentElement.classList.contains('theme-light') || !document.documentElement.classList.contains('dark');
  const tokens = typeof getChartThemeTokens === 'function' ? getChartThemeTokens(isLight) : null;
  const textColor = tokens ? tokens.legend : (isLight ? '#0f172a' : '#f8fafc');

  const defaultColors = getDonutPalette(isLight);

  const cleanData = (data || []).map(v => {
    const num = parseFloat(toEnglishDigits(v));
    return isNaN(num) ? 0 : num;
  });
  const cleanLabels = (labels || []).map(l => toEnglishDigits(l));

  const hasData = cleanData.some(v => v > 0);
  const chartLabels = hasData ? cleanLabels : ['بدون مصرف'];
  const chartValues = hasData ? cleanData : [1];
  const chartColors = hasData ? defaultColors.slice(0, chartLabels.length) : ['#334155'];

  const chartKey = canvas.id || containerId;
  if (window.chartInstances[chartKey]) {
    try {
      window.chartInstances[chartKey].destroy();
    } catch (e) {}
    delete window.chartInstances[chartKey];
  }

  const ctx = canvas.getContext('2d');
  window.chartInstances[chartKey] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: chartLabels,
      datasets: [{
        data: chartValues,
        backgroundColor: chartColors,
        borderColor: tokens ? tokens.pointBorder : (isLight ? '#ffffff' : '#0f172a'),
        borderWidth: 2,
        hoverOffset: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          rtl: true,
          labels: {
            boxWidth: 9,
            boxHeight: 9,
            usePointStyle: true,
            pointStyle: 'circle',
            color: () => {
              const curIsLight = document.documentElement.classList.contains('theme-light') || !document.documentElement.classList.contains('dark');
              return typeof getChartThemeTokens === 'function' ? getChartThemeTokens(curIsLight).legend : (curIsLight ? '#0f172a' : '#f8fafc');
            },
            font: { family: 'Vazirmatn', size: 10.5, weight: '600' },
            padding: 8,
            generateLabels: function(chart) {
              const data = chart.data;
              if (!data.labels?.length || !data.datasets?.length) return [];
              const dataset = data.datasets[0];
              const curIsLight = document.documentElement.classList.contains('theme-light') || !document.documentElement.classList.contains('dark');
              const curTextColor = typeof getChartThemeTokens === 'function' ? getChartThemeTokens(curIsLight).legend : (curIsLight ? '#0f172a' : '#f8fafc');
              return data.labels.map((label, i) => {
                const fill = Array.isArray(dataset.backgroundColor) ? dataset.backgroundColor[i] : dataset.backgroundColor;
                return {
                  text: label,
                  fontColor: curTextColor,
                  color: curTextColor,
                  fillStyle: fill,
                  strokeStyle: fill,
                  lineWidth: 0,
                  pointStyle: 'circle',
                  hidden: isNaN(dataset.data[i]) || chart.getDataVisibility(i) === false,
                  index: i,
                  datasetIndex: 0
                };
              });
            }
          }
        },
        tooltip: {
          rtl: true,
          textDirection: 'rtl',
          displayColors: true,
          backgroundColor: tokens?.tooltipBg || (isLight ? '#ffffff' : '#0f172a'),
          titleColor: tokens?.tooltipTitle || (isLight ? '#0f172a' : '#ffffff'),
          borderColor: isLight ? '#e2e8f0' : '#334155',
          borderWidth: 1,
          bodyColor: tokens?.tooltipBody || (isLight ? '#0369a1' : '#22d3ee'),
          titleFont: { family: 'Vazirmatn', size: 10, weight: 'bold' },
          bodyFont: { family: 'monospace', size: 11, weight: 'bold' },
          padding: 8,
          cornerRadius: 8,
          callbacks: {
            label: function(ctx) {
              if (!hasData) return 'بدون مصرف ثبت‌شده';
              const val = ctx.raw;
              if (isDevice) {
                return `${ctx.label}: ${toEnglishDigits(val)} دستگاه`;
              }
              return `${ctx.label}: ${fmtTraffic(val, { html: false, isolate: true })}`;
            }
          }
        }
      }
    }
  });
}

async function renderLineCurveChart(containerId, labels, data, peakHour = null) {
  let canvas = document.getElementById(containerId);
  if (!canvas) return;

  if (typeof Chart === 'undefined') {
    try {
      await ensureChart();
    } catch (e) {
      return;
    }
  }
  if (typeof Chart === 'undefined') return;

  if (canvas.tagName.toLowerCase() !== 'canvas') {
    let innerCanvas = canvas.querySelector('canvas');
    if (!innerCanvas) {
      canvas.innerHTML = '<canvas dir="ltr" class="w-full h-full"></canvas>';
      innerCanvas = canvas.querySelector('canvas');
    }
    canvas = innerCanvas;
  }
  if (canvas && !canvas.getAttribute('dir')) {
    canvas.setAttribute('dir', 'ltr');
  }

  const isLight = document.documentElement.classList.contains('theme-light');
  const tokens = typeof getChartThemeTokens === 'function' ? getChartThemeTokens(isLight) : null;
  const textColor = tokens ? tokens.tick : (isLight ? '#1e293b' : '#cbd5e1');
  const gridColor = tokens ? tokens.grid : (isLight ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.06)');

  if (typeof Chart !== 'undefined') {
    Chart.defaults.color = textColor;
  }

  const cleanData = (data || []).map(v => {
    const num = parseFloat(toEnglishDigits(v));
    return isNaN(num) ? 0 : num;
  });
  const cleanLabels = (labels || []).map(l => toEnglishDigits(l));

  const chartKey = canvas.id || containerId;
  if (window.chartInstances[chartKey]) {
    try {
      window.chartInstances[chartKey].destroy();
    } catch (e) {}
    delete window.chartInstances[chartKey];
  }

  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 150);
  gradient.addColorStop(0, isLight ? 'rgba(245, 158, 11, 0.35)' : 'rgba(245, 158, 11, 0.30)');
  gradient.addColorStop(1, 'rgba(245, 158, 11, 0.0)');

  window.chartInstances[chartKey] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: cleanLabels,
      datasets: [{
        label: 'مصرف ساعتی',
        data: cleanData,
        borderColor: tokens ? tokens.warn : (isLight ? '#d97706' : '#f59e0b'),
        borderWidth: 2,
        backgroundColor: gradient,
        fill: true,
        tension: 0.38,
        pointRadius: 1.5,
        pointHoverRadius: 5,
        pointBackgroundColor: tokens ? tokens.warn : (isLight ? '#d97706' : '#fbbf24'),
        pointBorderColor: tokens ? tokens.pointBorder : (isLight ? '#ffffff' : '#0f172a'),
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl: true,
          textDirection: 'rtl',
          displayColors: false,
          backgroundColor: tokens?.tooltipBg || (isLight ? '#ffffff' : '#0f172a'),
          titleColor: tokens?.tooltipTitle || (isLight ? '#0f172a' : '#ffffff'),
          borderColor: isLight ? '#e2e8f0' : '#334155',
          borderWidth: 1,
          bodyColor: tokens?.warn || '#fbbf24',
          titleFont: { family: 'Vazirmatn', size: 10, weight: 'bold' },
          bodyFont: { family: 'monospace', size: 11, weight: 'bold' },
          padding: 8,
          cornerRadius: 8,
          callbacks: {
            title: (items) => `بازه ${items[0]?.label || ''}`,
            label: (ctx) => `مصرف: ${fmtTraffic(ctx.raw, { html: false, isolate: true })}`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: {
            color: textColor,
            font: { family: 'monospace', size: 9.5, weight: isLight ? '600' : '500' },
            maxTicksLimit: 12,
          }
        },
        y: {
          position: 'left',
          beginAtZero: true,
          suggestedMax: cleanData.some(v => v > 0) ? undefined : 1,
          grid: { color: gridColor },
          border: { display: false },
          ticks: {
            color: textColor,
            font: { family: 'monospace', size: 9, weight: isLight ? '600' : '500' },
            callback: (v) => fmtTraffic(v, { html: false, isolate: true })
          }
        }
      }
    }
  });

  const peakBadge = document.getElementById('repPeakHourBadge');
  if (peakBadge && peakHour) {
    peakBadge.innerText = `Peak: ${peakHour}`;
  }
}

function renderTrafficSplit(splitData) {
  if (!splitData) return;
  const downGb = splitData.download_gb ?? 0;
  const upGb = splitData.upload_gb ?? 0;
  const downPct = splitData.download_percent ?? 85;
  const upPct = splitData.upload_percent ?? 15;

  const downGbEl = document.getElementById('repSplitDownGb');
  if (downGbEl) downGbEl.innerText = fmtTraffic(downGb, { html: false, isolate: true });
  const downPctEl = document.getElementById('repSplitDownPct');
  if (downPctEl) downPctEl.innerText = `${toEnglishDigits(downPct)}%`;

  const upGbEl = document.getElementById('repSplitUpGb');
  if (upGbEl) upGbEl.innerText = fmtTraffic(upGb, { html: false, isolate: true });
  const upPctEl = document.getElementById('repSplitUpPct');
  if (upPctEl) upPctEl.innerText = `${toEnglishDigits(upPct)}%`;

  const downBar = document.getElementById('repSplitDownBar');
  if (downBar) downBar.style.width = `${downPct}%`;
  const upBar = document.getElementById('repSplitUpBar');
  if (upBar) upBar.style.width = `${upPct}%`;

  const ratioBadge = document.getElementById('repUpDownRatioBadge');
  if (ratioBadge) {
    ratioBadge.innerText = `RX ${toEnglishDigits(downPct)}% / TX ${toEnglishDigits(upPct)}%`;
  }
}

function renderBurnRate(burnRate, sub) {
  if (!burnRate) return;
  const speedBadge = document.getElementById('repBurnSpeedBadge');
  const avgDailyEl = document.getElementById('repBurnAvgDaily');
  const projectedDaysEl = document.getElementById('repBurnProjectedDays');
  const analysisTextEl = document.getElementById('repBurnAnalysisText');
  const statusIconEl = document.getElementById('repBurnStatusIcon');
  const analysisBox = document.getElementById('repBurnAnalysisBox');

  const avgGb = burnRate.avg_daily_gb || 0;
  if (speedBadge) {
    speedBadge.innerText = avgGb > 0 ? fmtTraffic(avgGb, { html: false, isolate: true }) : 'کم‌مصرف';
  }

  if (avgDailyEl) {
    avgDailyEl.innerHTML = fmtTraffic(avgGb, { html: true });
  }

  const projDays = burnRate.projected_days;
  if (projectedDaysEl) {
    if (projDays != null && projDays > 0) {
      projectedDaysEl.innerText = `حدود ${toEnglishDigits(projDays)} روز`;
      if (burnRate.status === 'fast') {
        projectedDaysEl.className = 'font-mono text-amber-400 text-xs num-bidi';
      } else {
        projectedDaysEl.className = 'font-mono text-emerald-400 text-xs num-bidi';
      }
    } else if (burnRate.status === 'unlimited') {
      projectedDaysEl.innerText = 'نامحدود ♾️';
      projectedDaysEl.className = 'font-mono text-cyan-400 text-xs';
    } else if (burnRate.status === 'exhausted') {
      projectedDaysEl.innerText = 'پایان‌یافته';
      projectedDaysEl.className = 'font-mono text-rose-400 text-xs';
    } else {
      projectedDaysEl.innerText = '—';
      projectedDaysEl.className = 'font-mono text-slate-400 text-xs';
    }
  }

  if (analysisTextEl && burnRate.text) {
    analysisTextEl.innerText = burnRate.text;
  }

  if (statusIconEl) {
    if (burnRate.status === 'fast') {
      statusIconEl.innerText = '⚠️';
      if (analysisBox) {
        analysisBox.className = 'p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 flex items-start gap-2';
      }
    } else if (burnRate.status === 'safe') {
      statusIconEl.innerText = '✅';
      if (analysisBox) {
        analysisBox.className = 'p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-200 flex items-start gap-2';
      }
    } else if (burnRate.status === 'unlimited') {
      statusIconEl.innerText = '♾️';
      if (analysisBox) {
        analysisBox.className = 'p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-xs text-cyan-200 flex items-start gap-2';
      }
    } else {
      statusIconEl.innerText = '🎯';
      if (analysisBox) {
        analysisBox.className = 'p-2.5 rounded-xl bg-slate-900/40 border border-slate-700/40 text-xs text-slate-300 flex items-start gap-2';
      }
    }
  }
}

window.renderBarChart = renderBarChart;
window.renderNodeBreakdown = renderNodeBreakdown;
window.renderDonutChart = renderDonutChart;
window.renderLineCurveChart = renderLineCurveChart;
window.renderTrafficSplit = renderTrafficSplit;
window.renderBurnRate = renderBurnRate;
window.ensureChart = ensureChart;

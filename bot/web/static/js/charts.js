/**
 * RemnaStore Pro - Charts & Reporting Visualizers
 * DRY reusable chart and breakdown generators using Chart.js.
 */

window.chartInstances = window.chartInstances || {};

function renderBarChart(containerId, totals, labels, isMonthly = false) {
  let canvas = document.getElementById(containerId);
  if (!canvas) return;

  // If container is a div instead of a canvas, find or create canvas inside it
  if (canvas.tagName.toLowerCase() !== 'canvas') {
    let innerCanvas = canvas.querySelector('canvas');
    if (!innerCanvas) {
      canvas.innerHTML = '<canvas class="w-full h-full"></canvas>';
      innerCanvas = canvas.querySelector('canvas');
    }
    canvas = innerCanvas;
  }

  // Fallback if Chart.js is not yet loaded
  if (typeof Chart === 'undefined') {
    return;
  }

  const isLight = document.documentElement.classList.contains('theme-light');
  const textColor = isLight ? '#475569' : '#94a3b8';
  const gridColor = isLight ? 'rgba(0, 0, 0, 0.05)' : 'rgba(255, 255, 255, 0.06)';
  
  // Color palette
  const mainColor = isMonthly 
    ? (isLight ? 'rgba(147, 51, 234, 0.8)' : 'rgba(168, 85, 247, 0.85)')
    : (isLight ? 'rgba(37, 99, 235, 0.8)' : 'rgba(56, 189, 248, 0.85)');
  const borderColor = isMonthly
    ? (isLight ? '#7e22ce' : '#c084fc')
    : (isLight ? '#1d4ed8' : '#38bdf8');

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
          rtl: false,
          textDirection: 'ltr',
          displayColors: false,
          backgroundColor: isLight ? '#1e293b' : '#0f172a',
          titleColor: '#ffffff',
          bodyColor: '#38bdf8',
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
              const val = context.raw != null ? Number(context.raw).toFixed(2) : '0.00';
              return `\u200E${val} GB\u200E`;
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
            font: { family: 'Vazirmatn', size: 10, weight: '500' }
          }
        },
        y: {
          position: 'left',
          beginAtZero: true,
          grid: {
            color: gridColor,
          },
          border: { display: false },
          ticks: {
            color: textColor,
            font: { family: 'monospace', size: 9 },
            callback: function(val) {
              return `\u200E${val} GB\u200E`;
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
      <span class="font-bold text-slate-100 font-mono inline-block" dir="ltr">\u200E${toEnglishDigits(n.total_formatted || '0 GB')}\u200E</span>
    </div>
  `).join('');
}

function renderDonutChart(containerId, labels, data, isDevice = false) {
  let canvas = document.getElementById(containerId);
  if (!canvas) return;

  if (canvas.tagName.toLowerCase() !== 'canvas') {
    let innerCanvas = canvas.querySelector('canvas');
    if (!innerCanvas) {
      canvas.innerHTML = '<canvas class="w-full h-full"></canvas>';
      innerCanvas = canvas.querySelector('canvas');
    }
    canvas = innerCanvas;
  }

  if (typeof Chart === 'undefined') return;

  const isLight = document.documentElement.classList.contains('theme-light');
  const textColor = isLight ? '#475569' : '#94a3b8';

  const defaultColors = isDevice
    ? ['#10b981', '#06b6d4', '#6366f1', '#ec4899', '#f59e0b', '#64748b']
    : ['#06b6d4', '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ec4899'];

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
        borderColor: isLight ? '#ffffff' : '#0f172a',
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
            boxWidth: 8,
            boxHeight: 8,
            usePointStyle: true,
            pointStyle: 'circle',
            color: textColor,
            font: { family: 'Vazirmatn', size: 9 },
            padding: 8,
          }
        },
        tooltip: {
          rtl: false,
          textDirection: 'ltr',
          displayColors: true,
          backgroundColor: isLight ? '#1e293b' : '#0f172a',
          titleColor: '#ffffff',
          bodyColor: '#38bdf8',
          titleFont: { family: 'Vazirmatn', size: 10, weight: 'bold' },
          bodyFont: { family: 'monospace', size: 11, weight: 'bold' },
          padding: 8,
          cornerRadius: 8,
          callbacks: {
            label: function(ctx) {
              if (!hasData) return ' بدون مصرف ثبت‌شده';
              const val = ctx.raw;
              const unit = isDevice ? ' دستگاه' : ' GB';
              return ` \u200E${val}${unit}\u200E`;
            }
          }
        }
      }
    }
  });
}

function renderLineCurveChart(containerId, labels, data, peakHour = null) {
  let canvas = document.getElementById(containerId);
  if (!canvas) return;

  if (canvas.tagName.toLowerCase() !== 'canvas') {
    let innerCanvas = canvas.querySelector('canvas');
    if (!innerCanvas) {
      canvas.innerHTML = '<canvas class="w-full h-full"></canvas>';
      innerCanvas = canvas.querySelector('canvas');
    }
    canvas = innerCanvas;
  }

  if (typeof Chart === 'undefined') return;

  const isLight = document.documentElement.classList.contains('theme-light');
  const textColor = isLight ? '#475569' : '#94a3b8';
  const gridColor = isLight ? 'rgba(0, 0, 0, 0.05)' : 'rgba(255, 255, 255, 0.06)';

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
        borderColor: '#f59e0b',
        borderWidth: 2,
        backgroundColor: gradient,
        fill: true,
        tension: 0.38,
        pointRadius: 1.5,
        pointHoverRadius: 5,
        pointBackgroundColor: '#fbbf24',
        pointBorderColor: isLight ? '#ffffff' : '#0f172a',
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl: false,
          textDirection: 'ltr',
          displayColors: false,
          backgroundColor: isLight ? '#1e293b' : '#0f172a',
          titleColor: '#ffffff',
          bodyColor: '#fbbf24',
          titleFont: { family: 'Vazirmatn', size: 10, weight: 'bold' },
          bodyFont: { family: 'monospace', size: 11, weight: 'bold' },
          padding: 8,
          cornerRadius: 8,
          callbacks: {
            title: (items) => `بازه ${items[0]?.label || ''}`,
            label: (ctx) => ` \u200E${ctx.raw} GB\u200E`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: {
            color: textColor,
            font: { family: 'monospace', size: 8 },
            maxTicksLimit: 12,
          }
        },
        y: {
          position: 'left',
          beginAtZero: true,
          grid: { color: gridColor },
          border: { display: false },
          ticks: {
            color: textColor,
            font: { family: 'monospace', size: 8 },
            callback: (v) => `\u200E${v} G\u200E`
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
  if (downGbEl) downGbEl.innerText = `\u200E${toEnglishDigits(downGb)} GB\u200E`;
  const downPctEl = document.getElementById('repSplitDownPct');
  if (downPctEl) downPctEl.innerText = `${toEnglishDigits(downPct)}%`;

  const upGbEl = document.getElementById('repSplitUpGb');
  if (upGbEl) upGbEl.innerText = `\u200E${toEnglishDigits(upGb)} GB\u200E`;
  const upPctEl = document.getElementById('repSplitUpPct');
  if (upPctEl) upPctEl.innerText = `${toEnglishDigits(upPct)}%`;

  const downBar = document.getElementById('repSplitDownBar');
  if (downBar) downBar.style.width = `${downPct}%`;
  const upBar = document.getElementById('repSplitUpBar');
  if (upBar) upBar.style.width = `${upPct}%`;

  const ratioBadge = document.getElementById('repUpDownRatioBadge');
  if (ratioBadge) {
    ratioBadge.innerText = `RX ${downPct}% / TX ${upPct}%`;
  }
}

window.renderBarChart = renderBarChart;
window.renderNodeBreakdown = renderNodeBreakdown;
window.renderDonutChart = renderDonutChart;
window.renderLineCurveChart = renderLineCurveChart;
window.renderTrafficSplit = renderTrafficSplit;

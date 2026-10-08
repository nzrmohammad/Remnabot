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
            drawBorder: false
          },
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
    <div dir="ltr" class="bg-slate-900/60 p-2 rounded-lg flex items-center justify-between border border-slate-700/40">
      <span class="text-base">${n.flag || '🌐'}</span>
      <span class="font-bold text-slate-100 font-mono inline-block" dir="ltr">\u200E${toEnglishDigits(n.total_formatted || '0 GB')}\u200E</span>
    </div>
  `).join('');
}

window.renderBarChart = renderBarChart;
window.renderNodeBreakdown = renderNodeBreakdown;

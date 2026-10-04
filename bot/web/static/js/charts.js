/**
 * RemnaStore Pro - Charts & Reporting Visualizers
 * DRY reusable chart and breakdown generators.
 */

function renderBarChart(containerId, totals, labels, isMonthly = false) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const maxVal = Math.max(...totals, 0.1);
  const activeColor = isMonthly ? 'bg-purple-500 shadow-sm shadow-purple-500/50' : 'bg-indigo-500 shadow-sm shadow-indigo-500/50';
  const normalColor = isMonthly ? 'bg-indigo-600/80' : 'bg-blue-500';
  const zeroColor = isMonthly ? 'bg-slate-700/60' : 'bg-slate-700/60';
  const textHighlight = isMonthly ? 'text-purple-300' : 'text-indigo-300';
  const barWidth = isMonthly ? 'w-6' : 'w-4';

  container.innerHTML = totals.map((val, idx) => {
    const isZero = !val || val <= 0;
    const hPct = isZero ? (isMonthly ? 8 : 10) : Math.min(100, Math.max(15, Math.round((val / maxVal) * 90)));
    const isMax = val > 0 && val === Math.max(...totals);
    const valText = val > 0 ? val : (isMonthly ? '0' : '');
    const bgClass = isMax ? activeColor : (val > 0 ? normalColor : zeroColor);

    return `
      <div class="flex flex-col items-center gap-1 flex-1">
        <span class="text-[8px] font-mono ${isMonthly ? 'text-purple-300' : 'text-slate-400'}" dir="ltr">${valText}</span>
        <div class="${barWidth} ${bgClass} rounded-t transition-all duration-500" style="height: ${hPct}%;"></div>
        <span class="text-[9px] ${isMax ? `${textHighlight} font-bold` : 'text-slate-400'}">${labels[idx] || ''}</span>
      </div>
    `;
  }).join('');
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
    <div dir="ltr" class="bg-slate-900/60 p-2 rounded-lg flex items-center justify-between">
      <span class="text-base">${n.flag || '🌐'}</span>
      <span class="font-bold text-slate-100 font-mono">${n.total_formatted || '0 GB'}</span>
    </div>
  `).join('');
}

window.renderBarChart = renderBarChart;
window.renderNodeBreakdown = renderNodeBreakdown;

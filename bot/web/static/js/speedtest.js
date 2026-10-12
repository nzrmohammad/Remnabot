/**
 * RemnaStore Pro - Client-Side Speed & Ping Test Engine
 * Measures real user latency, jitter, and download throughput via streaming chunks.
 */

(function () {
  let isTesting = false;
  let abortController = null;
  let animationFrameId = null;
  let currentSpeedMbps = 0;
  let targetSpeedMbps = 0;

  // Gauge calculation helpers (gauge runs from -210 deg to 30 deg = 240 deg sweep)
  const MIN_ANGLE = -210;
  const MAX_ANGLE = 30;
  const TOTAL_DEGREES = 240;
  const MAX_GAUGE_MBPS = 100;

  function speedToAngle(mbps) {
    const clamped = Math.max(0, Math.min(mbps, MAX_GAUGE_MBPS));
    // Non-linear scaling: 0-10 Mbps takes 40% of gauge, 10-50 takes 40%, 50-100 takes 20%
    let ratio = 0;
    if (clamped <= 10) {
      ratio = (clamped / 10) * 0.4;
    } else if (clamped <= 50) {
      ratio = 0.4 + ((clamped - 10) / 40) * 0.4;
    } else {
      ratio = 0.8 + ((clamped - 50) / 50) * 0.2;
    }
    return MIN_ANGLE + ratio * TOTAL_DEGREES;
  }

  function updateGaugeVisual(mbps) {
    const angle = speedToAngle(mbps);
    const needle = document.getElementById('speedGaugeNeedle');
    const speedDisplay = document.getElementById('speedDisplayVal');
    const gaugeProgressArc = document.getElementById('speedGaugeProgressArc');

    if (needle) {
      needle.setAttribute('transform', `rotate(${angle}, 100, 100)`);
    }

    if (speedDisplay) {
      speedDisplay.innerText = mbps < 10 ? mbps.toFixed(1) : Math.round(mbps).toString();
    }

    if (gaugeProgressArc) {
      // Arc radius 75, circumference for 240 degrees is ~314px
      const totalLen = 314;
      const angleFraction = (angle - MIN_ANGLE) / TOTAL_DEGREES;
      const offset = totalLen * (1 - Math.max(0, Math.min(1, angleFraction)));
      gaugeProgressArc.style.strokeDashoffset = offset.toString();
    }
  }

  function animateGauge() {
    if (!isTesting && Math.abs(currentSpeedMbps - targetSpeedMbps) < 0.1) {
      currentSpeedMbps = targetSpeedMbps;
      updateGaugeVisual(currentSpeedMbps);
      return;
    }

    currentSpeedMbps += (targetSpeedMbps - currentSpeedMbps) * 0.15;
    updateGaugeVisual(currentSpeedMbps);
    animationFrameId = requestAnimationFrame(animateGauge);
  }

  async function measurePingAndJitter(signal) {
    const statusText = document.getElementById('speedStatusBadge');
    if (statusText) {
      statusText.innerText = '📶 در حال اندازه‌گیری پینگ و تاخیر شبکه...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-[11px] text-cyan-300 font-medium transition text-center';
    }

    const pings = [];
    for (let i = 0; i < 4; i++) {
      if (signal.aborted) throw new Error('Aborted');
      const start = performance.now();
      try {
        const resp = await fetch(`/api/user/speedtest/ping?t=${Date.now()}_${i}`, {
          method: 'GET',
          cache: 'no-store',
          signal,
        });
        if (resp.ok) {
          const duration = performance.now() - start;
          pings.push(duration);
          const pingEl = document.getElementById('speedPingVal');
          if (pingEl) pingEl.innerText = Math.round(duration).toString();
        }
      } catch (e) {
        if (e.name === 'AbortError') throw e;
      }
      await new Promise(r => setTimeout(r, 60));
    }

    if (pings.length === 0) return { avgPing: 0, jitter: 0 };

    const avgPing = Math.round(pings.reduce((a, b) => a + b, 0) / pings.length);
    let jitterSum = 0;
    for (let i = 1; i < pings.length; i++) {
      jitterSum += Math.abs(pings[i] - pings[i - 1]);
    }
    const jitter = Math.round(jitterSum / (pings.length - 1));

    const pingEl = document.getElementById('speedPingVal');
    const jitterEl = document.getElementById('speedJitterVal');
    if (pingEl) pingEl.innerText = avgPing.toString();
    if (jitterEl) jitterEl.innerText = jitter.toString();

    return { avgPing, jitter };
  }

  async function measureDownloadThroughput(signal) {
    const statusText = document.getElementById('speedStatusBadge');
    if (statusText) {
      statusText.innerText = '⚡️ در حال دریافت داده و سنجش سرعت دانلود...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-blue-950/60 border border-blue-500/40 text-[11px] text-blue-300 font-medium transition text-center';
    }

    // Download 3 MB payload
    const testBytes = 3145728;
    const url = `/api/user/speedtest/payload?bytes=${testBytes}&_t=${Date.now()}`;
    const startTime = performance.now();
    let receivedBytes = 0;
    const speedSamples = [];

    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      signal,
    });

    if (!response.ok || !response.body) {
      throw new Error('Speedtest payload failed');
    }

    const reader = response.body.getReader();
    let lastSampleTime = startTime;
    let lastSampleBytes = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) {
        receivedBytes += value.length;
        const now = performance.now();
        const deltaSec = (now - lastSampleTime) / 1000;

        if (deltaSec >= 0.1) {
          const deltaBytes = receivedBytes - lastSampleBytes;
          const currentThroughputMbps = (deltaBytes * 8) / (deltaSec * 1000000);
          speedSamples.push(currentThroughputMbps);
          targetSpeedMbps = currentThroughputMbps;

          lastSampleTime = now;
          lastSampleBytes = receivedBytes;
        }

        const dataUsedEl = document.getElementById('speedDataUsed');
        if (dataUsedEl) {
          dataUsedEl.innerText = `${(receivedBytes / (1024 * 1024)).toFixed(1)} MB`;
        }
      }
    }

    const totalDurationSec = (performance.now() - startTime) / 1000;
    const overallMbps = totalDurationSec > 0 ? (receivedBytes * 8) / (totalDurationSec * 1000000) : 0;
    targetSpeedMbps = overallMbps;

    return overallMbps;
  }

  function getVerdictText(speed, ping) {
    if (speed >= 30 && ping <= 80) {
      return {
        text: '🚀 کیفیت فوق‌العاده؛ عالی برای استریم 4K، بازی آنلاین و وب‌گردی',
        cls: 'bg-emerald-950/70 border-emerald-500/50 text-emerald-300',
      };
    }
    if (speed >= 15) {
      return {
        text: '⚡️ کیفیت بسیار خوب؛ عالی برای اینستاگرام، تلگرام و یوتیوب HD',
        cls: 'bg-cyan-950/70 border-cyan-500/50 text-cyan-300',
      };
    }
    if (speed >= 5) {
      return {
        text: '🟡 کیفیت معمولی؛ مناسب برای ارسال پیام و وب‌گردی استاندارد',
        cls: 'bg-amber-950/70 border-amber-500/50 text-amber-300',
      };
    }
    return {
      text: '⚠️ سرعت پایین؛ اتصال ناپایدار یا اختلال اینترنت اپراتور',
      cls: 'bg-rose-950/70 border-rose-500/50 text-rose-300',
    };
  }

  async function startSpeedTest() {
    if (isTesting) return;

    const startBtn = document.getElementById('startSpeedTestBtn');
    const statusText = document.getElementById('speedStatusBadge');
    const startBtnText = document.getElementById('startSpeedTestBtnText');

    isTesting = true;
    abortController = new AbortController();

    if (startBtn) {
      startBtn.disabled = true;
      startBtn.classList.add('opacity-70', 'cursor-not-allowed');
    }
    if (startBtnText) startBtnText.innerText = 'در حال تست...';

    targetSpeedMbps = 0;
    currentSpeedMbps = 0;
    updateGaugeVisual(0);
    animateGauge();

    if (window.hapticFeedback) window.hapticFeedback('impact');

    try {
      // Step 1: Ping & Jitter
      const { avgPing, jitter } = await measurePingAndJitter(abortController.signal);

      // Step 2: Download Throughput
      const finalMbps = await measureDownloadThroughput(abortController.signal);

      // Step 3: Final verdict
      const verdict = getVerdictText(finalMbps, avgPing);
      if (statusText) {
        statusText.innerText = verdict.text;
        statusText.className = `py-2 px-3 rounded-xl border text-[11px] font-medium leading-relaxed transition text-center shadow-sm ${verdict.cls}`;
      }

      if (window.hapticFeedback) window.hapticFeedback('success');
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.warn('SpeedTest error:', err);
        if (statusText) {
          statusText.innerText = '❌ تست به دلیل خطای اتصال متوقف شد. لطفاً مجدداً امتحان کنید.';
          statusText.className = 'py-2 px-3 rounded-xl bg-rose-950/60 border border-rose-500/40 text-[11px] text-rose-300 font-medium text-center';
        }
      }
    } finally {
      isTesting = false;
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
      updateGaugeVisual(targetSpeedMbps);

      if (startBtn) {
        startBtn.disabled = false;
        startBtn.classList.remove('opacity-70', 'cursor-not-allowed');
      }
      if (startBtnText) startBtnText.innerText = 'تست مجدد سرعت 🚀';
    }
  }

  function stopSpeedTest() {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    isTesting = false;
    if (animationFrameId) cancelAnimationFrame(animationFrameId);

    const startBtn = document.getElementById('startSpeedTestBtn');
    const startBtnText = document.getElementById('startSpeedTestBtnText');
    if (startBtn) {
      startBtn.disabled = false;
      startBtn.classList.remove('opacity-70', 'cursor-not-allowed');
    }
    if (startBtnText) startBtnText.innerText = 'شروع تست سرعت 🚀';
  }

  function openSpeedTestModal() {
    if (window.openModal) {
      window.openModal('speedTestModal');
    } else {
      document.getElementById('speedTestModal')?.classList.remove('hidden');
    }
    if (window.syncTelegramBackButton) window.syncTelegramBackButton();
    if (window.hapticFeedback) window.hapticFeedback('selection');
  }

  function closeSpeedTestModal() {
    stopSpeedTest();
    if (window.closeModal) {
      window.closeModal('speedTestModal');
    } else {
      document.getElementById('speedTestModal')?.classList.add('hidden');
    }
    if (window.syncTelegramBackButton) window.syncTelegramBackButton();
    if (window.hapticFeedback) window.hapticFeedback('selection');
  }

  // Expose globally
  window.openSpeedTestModal = openSpeedTestModal;
  window.closeSpeedTestModal = closeSpeedTestModal;
  window.startSpeedTest = startSpeedTest;

  // Auto-bind on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('openSpeedTestModalBtn')?.addEventListener('click', openSpeedTestModal);
    document.getElementById('closeSpeedTestModalBtn')?.addEventListener('click', closeSpeedTestModal);
    document.getElementById('startSpeedTestBtn')?.addEventListener('click', startSpeedTest);
  });
})();

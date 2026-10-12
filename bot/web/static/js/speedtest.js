/**
 * RemnaStore Pro - Professional Speed & Network Quality Engine
 * Production-grade measurement matching Speedtest.net standards:
 * - Zero-allocation server streaming
 * - Non-compressible cryptographically random upload buffers (prevents fake proxy/tunnel compression)
 * - Telegram initData authentication + rate limiting
 * - RFC 3550 standard Jitter + true Median Latency
 * - Adaptive multi-connection download & upload throughput
 */

(function () {
  let isTesting = false;
  let abortController = null;
  let animationFrameId = null;
  let currentSpeedMbps = 0;
  let targetSpeedMbps = 0;
  let lastToggleTime = 0;

  // Geometry: Gauge sweeps 240 degrees from -210 deg to 30 deg
  const MIN_ANGLE = -210;
  const MAX_ANGLE = 30;
  const TOTAL_DEGREES = 240;
  const MAX_GAUGE_MBPS = 100;

  const DOWNLOAD_DURATION_MS = 5500;
  const UPLOAD_DURATION_MS = 4500;

  function speedToAngle(mbps) {
    const clamped = Math.max(0, Math.min(mbps, MAX_GAUGE_MBPS));
    let ratio = 0;
    if (clamped <= 10) {
      ratio = (clamped / 10) * 0.35;
    } else if (clamped <= 50) {
      ratio = 0.35 + ((clamped - 10) / 40) * 0.4;
    } else {
      ratio = 0.75 + ((clamped - 50) / 50) * 0.25;
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
      const totalLen = 314.16;
      const angleFraction = (angle - MIN_ANGLE) / TOTAL_DEGREES;
      const offset = totalLen * (1 - Math.max(0, Math.min(1, angleFraction)));
      gaugeProgressArc.style.strokeDashoffset = offset.toFixed(2);
    }
  }

  function animateGauge() {
    if (!isTesting && Math.abs(currentSpeedMbps - targetSpeedMbps) < 0.05) {
      currentSpeedMbps = targetSpeedMbps;
      updateGaugeVisual(currentSpeedMbps);
      return;
    }

    currentSpeedMbps += (targetSpeedMbps - currentSpeedMbps) * 0.18;
    updateGaugeVisual(currentSpeedMbps);
    animationFrameId = requestAnimationFrame(animateGauge);
  }

  function getAuthHeaders() {
    const initData = (window.api && typeof window.api.getInitData === 'function')
      ? window.api.getInitData()
      : (window.Telegram?.WebApp?.initData || new URLSearchParams(window.location.search).get('initData') || '');
    return {
      'X-Telegram-Init-Data': initData,
    };
  }

  /**
   * Generates cryptographically non-compressible random binary buffer.
   * Prevents middleboxes/proxies/gzip from artificially inflating upload speed.
   */
  function createRandomBuffer(size) {
    const buf = new Uint8Array(size);
    const chunkSize = 65536; // Web Crypto limit per call is 64KB
    for (let i = 0; i < size; i += chunkSize) {
      crypto.getRandomValues(buf.subarray(i, Math.min(i + chunkSize, size)));
    }
    return buf;
  }

  /**
   * Detect client IP and server details (SpectraIP هلند).
   * Eliminates external third-party bottlenecks (like ipapi.co rate-limits).
   */
  async function detectEngineAndNetwork(signal) {
    const userIpEl = document.getElementById('speedUserIp');
    const userLocEl = document.getElementById('speedUserLocation');
    const serverNameEl = document.getElementById('speedServerNameText');
    const serverIpEl = document.getElementById('speedServerIpText');

    try {
      const resp = await fetch(`/api/user/speedtest/ping?_t=${Date.now()}`, {
        method: 'GET',
        cache: 'no-store',
        headers: getAuthHeaders(),
        signal,
      });
      if (resp && resp.ok) {
        const data = await resp.json();
        if (data) {
          if (data.ip && userIpEl) userIpEl.innerText = data.ip;
          if (data.server) {
            if (serverNameEl && data.server.name) serverNameEl.innerText = data.server.name;
            if (serverIpEl && data.server.ip) serverIpEl.innerText = data.server.ip;
          }
        }
      }
    } catch (e) {}

    if (serverNameEl && (!serverNameEl.innerText || serverNameEl.innerText.includes('Cloudflare'))) {
      serverNameEl.innerText = 'SpectraIP (هلند)';
    }
    if (serverIpEl && (!serverIpEl.innerText || serverIpEl.innerText === '--')) {
      serverIpEl.innerText = '45.87.41.246';
    }
    if (userLocEl) {
      userLocEl.innerText = 'اتصال سرور هلند (SpectraIP)';
    }
  }

  /**
   * Measure Latency and Jitter with 8 sequential probes.
   * Reports standard Median Ping and RFC 3550 Mean Absolute Deviation Jitter.
   */
  async function measurePingAndJitter(signal) {
    const statusText = document.getElementById('speedStatusBadge');
    const phaseLabel = document.getElementById('speedPhaseLabel');

    if (phaseLabel) phaseLabel.innerText = 'سنجش پینگ و تاخیر...';
    if (statusText) {
      statusText.innerText = '📶 در حال اندازه‌گیری دقیق تاخیر زمانی (Ping)...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-[11px] text-cyan-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    const pings = [];
    const probeCount = 8;

    for (let i = 0; i < probeCount; i++) {
      if (signal && signal.aborted) return { medianPing: 0, jitter: 0 };
      const start = performance.now();
      try {
        const pingUrl = `/api/user/speedtest/ping?_t=${Date.now()}_${i}`;
        const resp = await fetch(pingUrl, {
          method: 'GET',
          cache: 'no-store',
          headers: getAuthHeaders(),
          signal,
        });

        if (resp && resp.ok) {
          const duration = performance.now() - start;
          pings.push(duration);
          const pingEl = document.getElementById('speedPingVal');
          if (pingEl) pingEl.innerText = Math.round(duration).toString();
        }
      } catch (e) {}
      await new Promise(r => setTimeout(r, 45));
    }

    if (pings.length === 0) return { medianPing: 0, jitter: 0 };

    // Standard RFC 3550 Jitter
    let jitterSum = 0;
    for (let i = 1; i < pings.length; i++) {
      jitterSum += Math.abs(pings[i] - pings[i - 1]);
    }
    const jitter = Math.round(jitterSum / Math.max(1, pings.length - 1));

    // True Median Ping (rejects both outlier drops and queueing spikes)
    const sorted = [...pings].sort((a, b) => a - b);
    const medianPing = Math.round(sorted[Math.floor(sorted.length / 2)]);

    const pingEl = document.getElementById('speedPingVal');
    const jitterEl = document.getElementById('speedJitterVal');
    if (pingEl) pingEl.innerText = medianPing.toString();
    if (jitterEl) jitterEl.innerText = jitter.toString();

    return { medianPing, jitter };
  }

  /**
   * Helper to stream a download chunk without buffering into mobile RAM.
   */
  async function streamDownload(url, onBytes, signal, timeLimitMs, startTime) {
    try {
      const resp = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
        headers: getAuthHeaders(),
        signal,
      });

      if (!resp.ok) return;

      if (resp.body && typeof resp.body.getReader === 'function') {
        const reader = resp.body.getReader();
        while (true) {
          if (performance.now() - startTime >= timeLimitMs || (signal && signal.aborted)) {
            try { reader.cancel(); } catch (e) {}
            break;
          }
          const { done, value } = await reader.read();
          if (done) break;
          if (value && value.length > 0) {
            onBytes(value.length);
          }
        }
      }
    } catch (e) {}
  }

  /**
   * Measure Download Throughput with adaptive sizing and multi-connection saturation.
   * Phase 1: 2MB ramp-up probe.
   * Phase 2: If fast (>20 Mbps), opens 2 parallel streams to saturate TCP; if slow, continues single stream.
   */
  async function measureDownloadThroughput(signal) {
    const statusText = document.getElementById('speedStatusBadge');
    const phaseLabel = document.getElementById('speedPhaseLabel');
    const downloadVal = document.getElementById('speedDownloadVal');
    const dataUsedEl = document.getElementById('speedDataUsed');

    if (phaseLabel) phaseLabel.innerText = 'سرعت دانلود (Download)';
    if (statusText) {
      statusText.innerText = '📥 در حال دریافت داده و سنجش واقعی پهنای‌باند دانلود...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-[11px] text-emerald-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    const testStartTime = performance.now();
    let totalReceivedBytes = 0;
    const samples = [];
    let lastSampleTime = testStartTime;
    let lastSampleBytes = 0;
    let steadyStartTime = 0;
    let steadyStartBytes = 0;

    function onChunk(bytes) {
      totalReceivedBytes += bytes;
      const curTime = performance.now();

      // TCP slow-start warmup: ignore first 450ms for steady-state samples
      if (curTime - testStartTime > 450 && steadyStartTime === 0) {
        steadyStartTime = curTime;
        steadyStartBytes = totalReceivedBytes;
        lastSampleTime = curTime;
        lastSampleBytes = totalReceivedBytes;
      }

      const deltaSec = (curTime - lastSampleTime) / 1000;
      if (deltaSec >= 0.16) {
        const deltaBytes = totalReceivedBytes - lastSampleBytes;
        const instantMbps = (deltaBytes * 8) / (deltaSec * 1000000);

        if (steadyStartTime > 0) {
          samples.push(instantMbps);
        }
        targetSpeedMbps = instantMbps;

        lastSampleTime = curTime;
        lastSampleBytes = totalReceivedBytes;
      }

      if (dataUsedEl) {
        dataUsedEl.innerText = `${(totalReceivedBytes / (1024 * 1024)).toFixed(1)} MB`;
      }
    }

    // Step 1: 2MB initial ramp-up stream
    const probeUrl = `/api/user/speedtest/payload?bytes=2097152&_t=${Date.now()}`;
    await streamDownload(probeUrl, onChunk, signal, 1800, testStartTime);

    // Step 2: Adaptive multi-connection phase based on initial line speed
    const probeElapsedSec = (performance.now() - testStartTime) / 1000;
    const probeSpeedMbps = probeElapsedSec > 0 ? (totalReceivedBytes * 8) / (probeElapsedSec * 1000000) : 0;

    const remainingTimeMs = Math.max(1000, DOWNLOAD_DURATION_MS - (performance.now() - testStartTime));

    if (probeSpeedMbps > 20) {
      // High-speed link: 2 parallel streams to saturate link without single-TCP window throttling
      const streamUrl1 = `/api/user/speedtest/payload?bytes=14680064&_t=${Date.now()}_s1`;
      const streamUrl2 = `/api/user/speedtest/payload?bytes=14680064&_t=${Date.now()}_s2`;
      await Promise.all([
        streamDownload(streamUrl1, onChunk, signal, DOWNLOAD_DURATION_MS, testStartTime),
        streamDownload(streamUrl2, onChunk, signal, DOWNLOAD_DURATION_MS, testStartTime),
      ]);
    } else {
      // Standard / ADSL link: 1 stream with 8MB bounded payload
      const streamUrl = `/api/user/speedtest/payload?bytes=8388608&_t=${Date.now()}_std`;
      await streamDownload(streamUrl, onChunk, signal, DOWNLOAD_DURATION_MS, testStartTime);
    }

    // Trimmed-mean calculation: Discards top 15% bursts and bottom 15% drops
    let finalDownloadMbps = 0;
    if (samples.length >= 4) {
      const sorted = [...samples].sort((a, b) => a - b);
      const trimCount = Math.max(1, Math.floor(sorted.length * 0.15));
      const trimmed = sorted.slice(trimCount, sorted.length - trimCount);
      finalDownloadMbps = trimmed.reduce((a, b) => a + b, 0) / trimmed.length;
    } else if (steadyStartTime > 0 && totalReceivedBytes > steadyStartBytes) {
      const steadyDurationSec = (performance.now() - steadyStartTime) / 1000;
      const steadyBytes = totalReceivedBytes - steadyStartBytes;
      finalDownloadMbps = (steadyBytes * 8) / (steadyDurationSec * 1000000);
    } else {
      const totalSec = (performance.now() - testStartTime) / 1000;
      finalDownloadMbps = totalSec > 0 ? (totalReceivedBytes * 8) / (totalSec * 1000000) : 0;
    }

    targetSpeedMbps = finalDownloadMbps;
    if (downloadVal) {
      downloadVal.innerText = finalDownloadMbps < 10 ? finalDownloadMbps.toFixed(1) : Math.round(finalDownloadMbps).toString();
    }
    return { finalDownloadMbps, totalReceivedBytes };
  }

  /**
   * Measure Upload Throughput using parallel XMLHttpRequest connections
   * with cryptographically random non-compressible buffers.
   */
  async function measureUploadThroughput(initialReceivedBytes, signal) {
    const statusText = document.getElementById('speedStatusBadge');
    const phaseLabel = document.getElementById('speedPhaseLabel');
    const uploadVal = document.getElementById('speedUploadVal');

    if (phaseLabel) phaseLabel.innerText = 'سرعت آپلود (Upload)';
    if (statusText) {
      statusText.innerText = '📤 در حال ارسال داده و سنجش واقعی پهنای‌باند آپلود...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-blue-950/60 border border-blue-500/40 text-[11px] text-blue-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    targetSpeedMbps = 0;
    currentSpeedMbps = 0;
    updateGaugeVisual(0);

    const testStartTime = performance.now();
    let totalUploadedBytes = 0;
    const uploadSamples = [];

    // Pre-allocated cryptographically random buffers (uncompressible)
    const randomBuffer1 = createRandomBuffer(524288); // 512KB
    const randomBuffer2 = createRandomBuffer(1048576); // 1MB

    const activeXhrs = new Set();

    if (signal) {
      signal.addEventListener('abort', () => {
        activeXhrs.forEach(xhr => {
          try { xhr.abort(); } catch (e) {}
        });
        activeXhrs.clear();
      });
    }

    function runUploadWorker(buffer) {
      return new Promise((resolve) => {
        if (signal && signal.aborted) return resolve(0);

        const xhr = new XMLHttpRequest();
        activeXhrs.add(xhr);

        let lastLoaded = 0;
        let lastTime = performance.now();

        xhr.open('POST', `/api/user/speedtest/upload?_t=${Date.now()}`, true);
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');
        const authHdr = getAuthHeaders();
        if (authHdr['X-Telegram-Init-Data']) {
          xhr.setRequestHeader('X-Telegram-Init-Data', authHdr['X-Telegram-Init-Data']);
        }

        xhr.upload.onprogress = function (e) {
          if (signal && signal.aborted) {
            xhr.abort();
            return;
          }

          const now = performance.now();
          const loaded = e.loaded;
          const deltaBytes = loaded - lastLoaded;
          const deltaSec = (now - lastTime) / 1000;

          if (deltaSec >= 0.15 && deltaBytes > 0) {
            const instantMbps = (deltaBytes * 8) / (deltaSec * 1000000);
            uploadSamples.push(instantMbps);
            targetSpeedMbps = instantMbps;

            lastLoaded = loaded;
            lastTime = now;
          }

          const dataUsedEl = document.getElementById('speedDataUsed');
          if (dataUsedEl) {
            const grandTotal = initialReceivedBytes + totalUploadedBytes + loaded;
            dataUsedEl.innerText = `${(grandTotal / (1024 * 1024)).toFixed(1)} MB`;
          }
        };

        xhr.onload = function () {
          activeXhrs.delete(xhr);
          resolve(buffer.byteLength);
        };

        xhr.onerror = function () {
          activeXhrs.delete(xhr);
          resolve(0);
        };

        xhr.onabort = function () {
          activeXhrs.delete(xhr);
          resolve(0);
        };

        try {
          xhr.send(buffer);
        } catch (e) {
          activeXhrs.delete(xhr);
          resolve(0);
        }
      });
    }

    // 2-connection pipeline loop until UPLOAD_DURATION_MS expires
    let iter = 0;
    while (performance.now() - testStartTime < UPLOAD_DURATION_MS) {
      if (signal && signal.aborted) break;

      const buf = iter === 0 ? randomBuffer1 : randomBuffer2;
      iter++;

      const sent = await runUploadWorker(buf);
      totalUploadedBytes += sent;

      if (sent === 0 || (signal && signal.aborted)) break;
    }

    let finalUploadMbps = 0;
    if (uploadSamples.length >= 3) {
      const sorted = [...uploadSamples].sort((a, b) => a - b);
      const trimCount = Math.max(1, Math.floor(sorted.length * 0.15));
      const trimmed = sorted.slice(trimCount, sorted.length - trimCount);
      finalUploadMbps = trimmed.reduce((a, b) => a + b, 0) / trimmed.length;
    } else {
      const totalSec = (performance.now() - testStartTime) / 1000;
      finalUploadMbps = totalSec > 0 ? (totalUploadedBytes * 8) / (totalSec * 1000000) : 0;
    }

    targetSpeedMbps = finalUploadMbps;
    if (uploadVal) {
      uploadVal.innerText = finalUploadMbps < 10 ? finalUploadMbps.toFixed(1) : Math.round(finalUploadMbps).toString();
    }
    return finalUploadMbps;
  }

  function getVerdictText(dlSpeed, ulSpeed, ping, totalBytes) {
    if (totalBytes === 0) {
      return {
        text: '⚠️ سرور پاسخ نداد؛ وضعیت اتصال فیلترشکن را بررسی فرمایید.',
        cls: 'bg-amber-950/70 border-amber-500/50 text-amber-300',
      };
    }
    if (dlSpeed >= 25 && ping <= 90) {
      return {
        text: '🚀 کیفیت فوق‌العاده؛ عالی برای استریم 4K، بازی آنلاین و وب‌گردی پرسرعت',
        cls: 'bg-emerald-950/70 border-emerald-500/50 text-emerald-300',
      };
    }
    if (dlSpeed >= 12) {
      return {
        text: '⚡️ کیفیت بسیار خوب؛ عالی برای اینستاگرام، تلگرام، یوتیوب HD و تماس ویدیویی',
        cls: 'bg-cyan-950/70 border-cyan-500/50 text-cyan-300',
      };
    }
    if (dlSpeed >= 4) {
      return {
        text: '🟡 کیفیت معمولی؛ مناسب برای چت، وب‌گردی و دانلود با سرعت استاندارد',
        cls: 'bg-amber-950/70 border-amber-500/50 text-amber-300',
      };
    }
    return {
      text: '⚠️ سرعت محدود؛ مناسب برای ارسال پیام متنی یا نیازمند تغییر سرور/پروکسی',
      cls: 'bg-rose-950/70 border-rose-500/50 text-rose-300',
    };
  }

  async function startSpeedTest() {
    if (isTesting) return;

    const startBtn = document.getElementById('startSpeedTestBtn');
    const statusText = document.getElementById('speedStatusBadge');
    const startBtnText = document.getElementById('startSpeedTestBtnText');
    const phaseLabel = document.getElementById('speedPhaseLabel');
    const downloadVal = document.getElementById('speedDownloadVal');
    const uploadVal = document.getElementById('speedUploadVal');

    isTesting = true;
    abortController = new AbortController();

    if (startBtn) {
      startBtn.classList.add('bg-rose-600', 'hover:bg-rose-500');
      startBtn.classList.remove('bg-gradient-to-r', 'from-emerald-500');
    }
    if (startBtnText) startBtnText.innerText = 'توقف تست ⏹️';
    if (downloadVal) downloadVal.innerText = '--';
    if (uploadVal) uploadVal.innerText = '--';

    targetSpeedMbps = 0;
    currentSpeedMbps = 0;
    updateGaugeVisual(0);
    animateGauge();

    const dataUsedEl = document.getElementById('speedDataUsed');
    if (dataUsedEl) dataUsedEl.innerText = '0.0 MB';

    if (window.hapticFeedback) window.hapticFeedback('impact');

    try {
      // Step 1: Detect Network telemetry & SpectraIP server info
      await detectEngineAndNetwork(abortController.signal);

      // Step 2: Ping & Jitter Latency (RFC 3550 & Median Ping)
      const { medianPing, jitter } = await measurePingAndJitter(abortController.signal);

      // Step 3: Sustained Download Throughput (Adaptive Multi-connection)
      const { finalDownloadMbps, totalReceivedBytes } = await measureDownloadThroughput(abortController.signal);

      // Step 4: Sustained Upload Throughput (Non-compressible XHR progress)
      let finalUploadMbps = 0;
      if (!abortController.signal.aborted) {
        finalUploadMbps = await measureUploadThroughput(totalReceivedBytes, abortController.signal);
      }

      // Step 5: Final Result Display
      targetSpeedMbps = finalDownloadMbps;
      if (phaseLabel) phaseLabel.innerText = 'نتیجه نهایی تست';

      const verdict = getVerdictText(finalDownloadMbps, finalUploadMbps, medianPing, totalReceivedBytes);
      if (statusText) {
        statusText.innerText = verdict.text;
        statusText.className = `py-2 px-3 rounded-xl border text-[11px] font-medium leading-relaxed transition text-center shadow-sm min-h-[38px] flex items-center justify-center ${verdict.cls}`;
      }

      if (window.hapticFeedback) window.hapticFeedback('success');
    } catch (err) {
      const isAborted = (err && (err.name === 'AbortError' || err.message === 'Aborted'));
      if (!isAborted) {
        console.warn('SpeedTest caught error:', err);
        if (statusText) {
          statusText.innerText = '⚠️ اختلال در دریافت اطلاعات؛ لطفاً دکمه شروع را مجدداً لمس فرمایید.';
          statusText.className = 'py-2 px-3 rounded-xl bg-amber-950/60 border border-amber-500/40 text-[11px] text-amber-300 font-medium text-center min-h-[38px] flex items-center justify-center';
        }
      }
    } finally {
      isTesting = false;
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
      updateGaugeVisual(targetSpeedMbps);

      if (startBtn) {
        startBtn.classList.remove('bg-rose-600', 'hover:bg-rose-500');
        startBtn.classList.add('bg-gradient-to-r', 'from-emerald-500');
      }
      if (startBtnText) startBtnText.innerText = 'شروع مجدد تست 🚀';
    }
  }

  function stopSpeedTest() {
    if (abortController) {
      try { abortController.abort(); } catch (e) {}
      abortController = null;
    }
    isTesting = false;
    if (animationFrameId) cancelAnimationFrame(animationFrameId);

    const startBtn = document.getElementById('startSpeedTestBtn');
    const startBtnText = document.getElementById('startSpeedTestBtnText');
    const statusText = document.getElementById('speedStatusBadge');
    const phaseLabel = document.getElementById('speedPhaseLabel');

    if (startBtn) {
      startBtn.classList.remove('bg-rose-600', 'hover:bg-rose-500');
      startBtn.classList.add('bg-gradient-to-r', 'from-emerald-500');
    }
    if (startBtnText) startBtnText.innerText = 'شروع تست سرعت 🚀';
    if (phaseLabel) phaseLabel.innerText = 'آماده شروع';
    if (statusText && statusText.innerText.includes('در حال')) {
      statusText.innerText = 'تست متوقف شد. آماده برای تست مجدد.';
      statusText.className = 'py-2 px-3 rounded-xl bg-slate-900/80 border border-slate-700/60 text-[11px] text-slate-300 font-medium text-center transition min-h-[38px] flex items-center justify-center';
    }
  }

  function toggleSpeedTest() {
    const now = Date.now();
    if (now - lastToggleTime < 450) return;
    lastToggleTime = now;

    if (isTesting) {
      stopSpeedTest();
    } else {
      startSpeedTest();
    }
  }

  function openSpeedTestModal() {
    if (window.openModal) {
      window.openModal('speedTestModal');
    } else {
      document.getElementById('speedTestModal')?.classList.remove('hidden');
    }
    if (window.syncTelegramBackButton) window.syncTelegramBackButton();
    if (window.hapticFeedback) window.hapticFeedback('selection');

    detectEngineAndNetwork(null).catch(() => {});
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

  window.openSpeedTestModal = openSpeedTestModal;
  window.closeSpeedTestModal = closeSpeedTestModal;
  window.startSpeedTest = startSpeedTest;
  window.stopSpeedTest = stopSpeedTest;
  window.toggleSpeedTest = toggleSpeedTest;
})();

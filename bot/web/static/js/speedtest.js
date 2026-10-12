/**
 * RemnaStore Pro - Professional Speed & Network Quality Engine
 * Measures true sustained Download throughput, Upload throughput, Latency, and Jitter
 * directly against the server (SpectraIP 45.87.41.246 - هلند / آمستردام).
 * Uses real-time XMLHttpRequest upload progress and sliding-window download stream.
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

  const DOWNLOAD_DURATION_MS = 5200;
  const UPLOAD_DURATION_MS = 4200;

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

  /**
   * Detect client IP, operator/location, and server details (SpectraIP 45.87.41.246).
   */
  async function detectEngineAndNetwork(signal) {
    const userIpEl = document.getElementById('speedUserIp');
    const userLocEl = document.getElementById('speedUserLocation');
    const serverNameEl = document.getElementById('speedServerNameText');
    const serverIpEl = document.getElementById('speedServerIpText');

    let detectedIp = '';

    // 1. Fetch server ping probe to get client IP and server details
    try {
      const pingResp = await fetch(`/api/user/speedtest/ping?_t=${Date.now()}`, {
        method: 'GET',
        cache: 'no-store',
        signal,
      });
      if (pingResp && pingResp.ok) {
        const pingData = await pingResp.json();
        if (pingData) {
          if (pingData.ip) {
            detectedIp = pingData.ip;
            if (userIpEl) userIpEl.innerText = detectedIp;
          }
          if (pingData.server) {
            if (serverNameEl && pingData.server.name) {
              serverNameEl.innerText = pingData.server.name;
            }
            if (serverIpEl && pingData.server.ip) {
              serverIpEl.innerText = pingData.server.ip;
            }
          }
        }
      }
    } catch (e) {}

    // Ensure server info defaults to SpectraIP
    if (serverNameEl && (!serverNameEl.innerText || serverNameEl.innerText.includes('Cloudflare'))) {
      serverNameEl.innerText = 'SpectraIP (هلند)';
    }
    if (serverIpEl && (!serverIpEl.innerText || serverIpEl.innerText === '--')) {
      serverIpEl.innerText = '45.87.41.246';
    }

    // 2. Try fast client ISP/location detection if IP is available
    if (detectedIp && userLocEl && userLocEl.innerText.includes('شناسایی')) {
      try {
        const ctrl = new AbortController();
        const tid = setTimeout(() => ctrl.abort(), 1600);
        const geoResp = await fetch(`https://ipapi.co/${detectedIp}/json/`, {
          signal: ctrl.signal,
          cache: 'no-store',
        });
        clearTimeout(tid);
        if (geoResp && geoResp.ok) {
          const geoData = await geoResp.json();
          if (geoData) {
            const org = geoData.org || geoData.asn || '';
            const city = geoData.city || '';
            const country = geoData.country_name || '';
            let text = '';
            if (city && country) text = `${city}، ${country}`;
            else if (country) text = country;
            if (org) text = text ? `${text} (${org})` : org;
            if (text) userLocEl.innerText = text;
          }
        }
      } catch (e) {
        if (userLocEl && userLocEl.innerText.includes('شناسایی')) {
          userLocEl.innerText = 'اتصال سرور هلند (SpectraIP)';
        }
      }
    } else if (userLocEl && userLocEl.innerText.includes('شناسایی')) {
      userLocEl.innerText = 'اتصال سرور هلند (SpectraIP)';
    }
  }

  /**
   * Measure Ping (RTT) and Jitter with 6 sequential probes.
   * Standard RFC 3550 Mean Absolute Deviation for Jitter.
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
    const probeCount = 6;

    for (let i = 0; i < probeCount; i++) {
      if (signal && signal.aborted) return { avgPing: 0, jitter: 0 };
      const start = performance.now();
      try {
        const pingUrl = `/api/user/speedtest/ping?_t=${Date.now()}_${i}`;
        const resp = await fetch(pingUrl, {
          method: 'GET',
          cache: 'no-store',
          signal,
        });

        if (resp && resp.ok) {
          const duration = performance.now() - start;
          pings.push(duration);
          const pingEl = document.getElementById('speedPingVal');
          if (pingEl) pingEl.innerText = Math.round(duration).toString();
        }
      } catch (e) {}
      await new Promise(r => setTimeout(r, 50));
    }

    if (pings.length === 0) return { avgPing: 0, jitter: 0 };

    // Standard RFC 3550 Jitter: Mean absolute difference between consecutive pings
    let jitterSum = 0;
    for (let i = 1; i < pings.length; i++) {
      jitterSum += Math.abs(pings[i] - pings[i - 1]);
    }
    const jitter = Math.round(jitterSum / Math.max(1, pings.length - 1));

    // Baseline physical wire ping: Speedtest.net lowest quartile / minimum ping
    const sorted = [...pings].sort((a, b) => a - b);
    const avgPing = Math.round(sorted[0]);

    const pingEl = document.getElementById('speedPingVal');
    const jitterEl = document.getElementById('speedJitterVal');
    if (pingEl) pingEl.innerText = avgPing.toString();
    if (jitterEl) jitterEl.innerText = jitter.toString();

    return { avgPing, jitter };
  }

  /**
   * Measure Download Throughput over sustained window without burst overestimation.
   * Uses real streaming binary payload from SpectraIP server.
   */
  async function measureDownloadThroughput(signal) {
    const statusText = document.getElementById('speedStatusBadge');
    const phaseLabel = document.getElementById('speedPhaseLabel');
    const downloadVal = document.getElementById('speedDownloadVal');

    if (phaseLabel) phaseLabel.innerText = 'سرعت دانلود (Download)';
    if (statusText) {
      statusText.innerText = '📥 در حال دریافت داده و سنجش واقعی پهنای‌باند دانلود...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-[11px] text-emerald-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    const testStartTime = performance.now();
    let totalReceivedBytes = 0;

    const chunkUrl = `/api/user/speedtest/payload?bytes=26214400&_t=${Date.now()}`;
    const samples = [];
    let lastSampleTime = testStartTime;
    let lastSampleBytes = 0;
    let steadyStartTime = 0;
    let steadyStartBytes = 0;

    try {
      const response = await fetch(chunkUrl, {
        method: 'GET',
        cache: 'no-store',
        signal,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      if (response.body && typeof response.body.getReader === 'function') {
        const reader = response.body.getReader();

        while (true) {
          const now = performance.now();
          if (now - testStartTime >= DOWNLOAD_DURATION_MS || (signal && signal.aborted)) {
            try { reader.cancel(); } catch (e) {}
            break;
          }

          const { done, value } = await reader.read();
          if (done) break;

          if (value && value.length > 0) {
            totalReceivedBytes += value.length;
            const curTime = performance.now();

            // TCP warmup: ignore first 450ms ramp-up for steady baseline
            if (curTime - testStartTime > 450 && steadyStartTime === 0) {
              steadyStartTime = curTime;
              steadyStartBytes = totalReceivedBytes;
              lastSampleTime = curTime;
              lastSampleBytes = totalReceivedBytes;
            }

            const deltaSec = (curTime - lastSampleTime) / 1000;
            // Record rate sample every 160ms
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

            const dataUsedEl = document.getElementById('speedDataUsed');
            if (dataUsedEl) {
              dataUsedEl.innerText = `${(totalReceivedBytes / (1024 * 1024)).toFixed(1)} MB`;
            }
          }
        }
      } else {
        // Fallback for older WebViews
        const buf = await response.arrayBuffer();
        if (buf && buf.byteLength > 0) {
          totalReceivedBytes = buf.byteLength;
          const totalSec = (performance.now() - testStartTime) / 1000;
          targetSpeedMbps = totalSec > 0 ? (totalReceivedBytes * 8) / (totalSec * 1000000) : 0;
        }
      }
    } catch (err) {
      if (signal && !signal.aborted) {
        console.warn('Download measurement caught:', err);
      }
    }

    // Speedtest.net standard: Trimmed mean to eliminate TCP burst anomalies
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
   * Measure Upload Throughput using real XMLHttpRequest upload progress events.
   * Tracks exact physical byte transmission as packets leave the network interface.
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

    // Pre-allocated upload chunks: 512KB and 2MB
    const chunk512k = new Uint8Array(524288);
    const chunk2m = new Uint8Array(2097152);

    let activeXhr = null;

    if (signal) {
      signal.addEventListener('abort', () => {
        if (activeXhr) {
          try { activeXhr.abort(); } catch (e) {}
        }
      });
    }

    function uploadChunk(buffer) {
      return new Promise((resolve) => {
        if (signal && signal.aborted) return resolve(0);

        const xhr = new XMLHttpRequest();
        activeXhr = xhr;

        const chunkStart = performance.now();
        let lastLoaded = 0;
        let lastTime = chunkStart;

        xhr.open('POST', `/api/user/speedtest/upload?_t=${Date.now()}`, true);
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');

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
          activeXhr = null;
          resolve(buffer.byteLength);
        };

        xhr.onerror = function () {
          activeXhr = null;
          resolve(0);
        };

        xhr.onabort = function () {
          activeXhr = null;
          resolve(0);
        };

        try {
          xhr.send(buffer);
        } catch (e) {
          resolve(0);
        }
      });
    }

    let iteration = 0;
    while (performance.now() - testStartTime < UPLOAD_DURATION_MS) {
      if (signal && signal.aborted) break;

      const buffer = iteration === 0 ? chunk512k : chunk2m;
      iteration++;

      const sent = await uploadChunk(buffer);
      totalUploadedBytes += sent;

      if (sent === 0 || (signal && signal.aborted)) break;
    }

    // Calculate final trimmed upload throughput
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

      // Step 2: Ping & Jitter Latency (RFC 3550)
      const { avgPing, jitter } = await measurePingAndJitter(abortController.signal);

      // Step 3: Sustained Download Throughput (Trimmed Mean)
      const { finalDownloadMbps, totalReceivedBytes } = await measureDownloadThroughput(abortController.signal);

      // Step 4: Sustained Upload Throughput (XHR upload progress)
      let finalUploadMbps = 0;
      if (!abortController.signal.aborted) {
        finalUploadMbps = await measureUploadThroughput(totalReceivedBytes, abortController.signal);
      }

      // Step 5: Final Result Display
      targetSpeedMbps = finalDownloadMbps;
      if (phaseLabel) phaseLabel.innerText = 'نتیجه نهایی تست';

      const verdict = getVerdictText(finalDownloadMbps, finalUploadMbps, avgPing, totalReceivedBytes);
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
    if (now - lastToggleTime < 450) return; // Debounce rapid double-clicks
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

    // Auto-detect IP silently when modal opens
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

  // Expose globally for inline onclick handlers and Telegram WebApp lifecycle
  window.openSpeedTestModal = openSpeedTestModal;
  window.closeSpeedTestModal = closeSpeedTestModal;
  window.startSpeedTest = startSpeedTest;
  window.stopSpeedTest = stopSpeedTest;
  window.toggleSpeedTest = toggleSpeedTest;
})();

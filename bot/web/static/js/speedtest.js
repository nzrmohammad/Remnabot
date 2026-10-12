/**
 * RemnaStore Pro - Professional Speed & Network Quality Engine
 * Measures true sustained Download throughput, Upload throughput, Latency, and Jitter.
 * Includes user IP telemetry and multi-CDN support without burst overestimation.
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

  const DOWNLOAD_DURATION_MS = 3800;
  const UPLOAD_DURATION_MS = 2500;

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
   * Detect client IP, operator, and select fastest test engine (Cloudflare vs Proxy Server).
   */
  async function detectEngineAndNetwork(signal) {
    const userIpEl = document.getElementById('speedUserIp');
    const userLocEl = document.getElementById('speedUserLocation');
    const serverNameEl = document.getElementById('speedServerNameText');

    let source = 'server';

    // 1. Fetch server ping first to get authoritative user IP
    try {
      const pingResp = await fetch(`/api/user/speedtest/ping?_t=${Date.now()}`, {
        method: 'GET',
        cache: 'no-store',
        signal,
      });
      if (pingResp && pingResp.ok) {
        const pingData = await pingResp.json();
        if (pingData && pingData.ip && userIpEl) {
          userIpEl.innerText = pingData.ip;
        }
      }
    } catch (e) {}

    // 2. Probe Cloudflare CDN availability
    try {
      const probeController = new AbortController();
      const timeoutId = setTimeout(() => probeController.abort(), 1800);

      const resp = await fetch(`https://speed.cloudflare.com/__down?bytes=0&_t=${Date.now()}`, {
        method: 'GET',
        cache: 'no-store',
        signal: probeController.signal,
      });
      clearTimeout(timeoutId);

      if (resp && resp.ok) {
        source = 'cloudflare';
        const cfIp = resp.headers.get('cf-meta-ip');
        const cfCity = resp.headers.get('cf-meta-city');
        const cfCountry = resp.headers.get('cf-meta-country');
        const cfAsn = resp.headers.get('cf-meta-asn');

        if (cfIp && userIpEl) userIpEl.innerText = cfIp;

        let locStr = '';
        if (cfCity && cfCountry) locStr = `${cfCity}, ${cfCountry}`;
        else if (cfCountry) locStr = `کشور: ${cfCountry}`;
        if (cfAsn) locStr += ` (${cfAsn})`;

        if (userLocEl) {
          userLocEl.innerText = locStr || 'اتصال پایدار (Cloudflare Edge)';
        }
        if (serverNameEl) {
          serverNameEl.innerText = 'شبکه جهانی Cloudflare';
        }
        return source;
      }
    } catch (e) {
      // Cloudflare unavailable -> fallback to proxy server
    }

    if (serverNameEl) {
      serverNameEl.innerText = 'سرور پروکسی اشتراک';
    }
    if (userLocEl && userLocEl.innerText.includes('شناسایی')) {
      userLocEl.innerText = 'اتصال مستقیم سرور';
    }
    return source;
  }

  /**
   * Measure Ping (RTT) and Jitter with sequential probes.
   */
  async function measurePingAndJitter(source, signal) {
    const statusText = document.getElementById('speedStatusBadge');
    const phaseLabel = document.getElementById('speedPhaseLabel');

    if (phaseLabel) phaseLabel.innerText = 'سنجش پینگ و تاخیر...';
    if (statusText) {
      statusText.innerText = '📶 در حال اندازه‌گیری دقیق تاخیر زمانی (Ping)...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-[11px] text-cyan-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    const pings = [];
    const probeCount = 3;

    for (let i = 0; i < probeCount; i++) {
      if (signal && signal.aborted) return { avgPing: 0, jitter: 0 };
      const start = performance.now();
      try {
        const pingUrl = source === 'cloudflare'
          ? `https://speed.cloudflare.com/__down?bytes=0&_t=${Date.now()}_${i}`
          : `/api/user/speedtest/ping?t=${Date.now()}_${i}`;

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
      await new Promise(r => setTimeout(r, 60));
    }

    if (pings.length === 0) return { avgPing: 0, jitter: 0 };

    const avgPing = Math.round(pings.reduce((a, b) => a + b, 0) / pings.length);
    let jitterSum = 0;
    for (let i = 1; i < pings.length; i++) {
      jitterSum += Math.abs(pings[i] - pings[i - 1]);
    }
    const jitter = Math.round(jitterSum / Math.max(1, pings.length - 1));

    const pingEl = document.getElementById('speedPingVal');
    const jitterEl = document.getElementById('speedJitterVal');
    if (pingEl) pingEl.innerText = avgPing.toString();
    if (jitterEl) jitterEl.innerText = jitter.toString();

    return { avgPing, jitter };
  }

  /**
   * Measure Download Throughput over sustained window without burst overestimation.
   */
  async function measureDownloadThroughput(initialSource, signal) {
    const statusText = document.getElementById('speedStatusBadge');
    const phaseLabel = document.getElementById('speedPhaseLabel');
    const downloadVal = document.getElementById('speedDownloadVal');

    if (phaseLabel) phaseLabel.innerText = 'سرعت دانلود (Download)';
    if (statusText) {
      statusText.innerText = '📥 در حال دریافت داده و سنجش واقعی پهنای‌باند دانلود...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-[11px] text-emerald-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    let activeSource = initialSource;
    const testStartTime = performance.now();
    let totalReceivedBytes = 0;

    // TCP warm-up tracking: ignore first 400ms for stable wire throughput
    let steadyStartTime = 0;
    let steadyStartBytes = 0;

    const chunkSizes = [524288, 1048576, 2097152, 4194304, 8388608];
    let chunkIndex = 0;
    let lastTickTime = testStartTime;
    let lastTickBytes = 0;

    while (performance.now() - testStartTime < DOWNLOAD_DURATION_MS) {
      if (signal && signal.aborted) break;

      const bytesToFetch = chunkSizes[Math.min(chunkIndex, chunkSizes.length - 1)];
      chunkIndex++;

      const chunkUrl = activeSource === 'cloudflare'
        ? `https://speed.cloudflare.com/__down?bytes=${bytesToFetch}&_t=${Date.now()}`
        : `/api/user/speedtest/payload?bytes=${bytesToFetch}&_t=${Date.now()}`;

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
            if (performance.now() - testStartTime >= DOWNLOAD_DURATION_MS || (signal && signal.aborted)) {
              try { reader.cancel(); } catch (e) {}
              break;
            }

            const { done, value } = await reader.read();
            if (done) break;

            if (value && value.length > 0) {
              totalReceivedBytes += value.length;
              const now = performance.now();

              // Mark steady state after initial 400ms buffer
              if (now - testStartTime > 400 && steadyStartTime === 0) {
                steadyStartTime = now;
                steadyStartBytes = totalReceivedBytes;
              }

              const deltaSec = (now - lastTickTime) / 1000;
              if (deltaSec >= 0.12) {
                // Compute true physical wire rate over steady window
                if (steadyStartTime > 0) {
                  const sustainedSec = (now - steadyStartTime) / 1000;
                  const sustainedBytes = totalReceivedBytes - steadyStartBytes;
                  targetSpeedMbps = (sustainedBytes * 8) / (sustainedSec * 1000000);
                } else {
                  targetSpeedMbps = ((totalReceivedBytes - lastTickBytes) * 8) / (deltaSec * 1000000);
                }

                lastTickTime = now;
                lastTickBytes = totalReceivedBytes;
              }

              const dataUsedEl = document.getElementById('speedDataUsed');
              if (dataUsedEl) {
                dataUsedEl.innerText = `${(totalReceivedBytes / (1024 * 1024)).toFixed(1)} MB`;
              }
            }
          }
        } else {
          // ArrayBuffer fallback for WebViews
          const buf = await response.arrayBuffer();
          if (buf && buf.byteLength > 0) {
            totalReceivedBytes += buf.byteLength;
            const now = performance.now();
            const deltaSec = (now - testStartTime) / 1000;
            targetSpeedMbps = deltaSec > 0 ? (totalReceivedBytes * 8) / (deltaSec * 1000000) : 0;

            const dataUsedEl = document.getElementById('speedDataUsed');
            if (dataUsedEl) {
              dataUsedEl.innerText = `${(totalReceivedBytes / (1024 * 1024)).toFixed(1)} MB`;
            }
          }
        }
      } catch (err) {
        if (signal && signal.aborted) break;
        if (activeSource === 'cloudflare') {
          activeSource = 'server';
          const serverNameEl = document.getElementById('speedServerNameText');
          if (serverNameEl) serverNameEl.innerText = 'سرور پروکسی اشتراک (فال‌بک)';
          await new Promise(r => setTimeout(r, 80));
          continue;
        }
        break;
      }
    }

    // Accurate sustained physical wire throughput calculation
    let finalDownloadMbps = 0;
    if (steadyStartTime > 0 && totalReceivedBytes > steadyStartBytes) {
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
   * Measure Upload Throughput by streaming synthetic buffers to server.
   */
  async function measureUploadThroughput(initialSource, signal) {
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
    let totalSentBytes = 0;

    // Upload payload buffers (256 KB, 512 KB, 1 MB)
    const uploadPayloads = [
      new Uint8Array(262144),
      new Uint8Array(524288),
      new Uint8Array(1048576),
    ];
    let payloadIdx = 0;

    while (performance.now() - testStartTime < UPLOAD_DURATION_MS) {
      if (signal && signal.aborted) break;

      const payload = uploadPayloads[Math.min(payloadIdx, uploadPayloads.length - 1)];
      payloadIdx++;

      const chunkStart = performance.now();
      try {
        const uploadUrl = initialSource === 'cloudflare'
          ? 'https://speed.cloudflare.com/__up'
          : '/api/user/speedtest/upload';

        const resp = await fetch(uploadUrl, {
          method: 'POST',
          body: payload,
          cache: 'no-store',
          signal,
        });

        if (resp && resp.ok) {
          totalSentBytes += payload.byteLength;
          const now = performance.now();
          const totalSec = (now - testStartTime) / 1000;
          if (totalSec > 0.1) {
            targetSpeedMbps = (totalSentBytes * 8) / (totalSec * 1000000);
          }
        }
      } catch (e) {
        if (signal && signal.aborted) break;
        // Fallback to local server upload if Cloudflare POST blocked
        try {
          const resp = await fetch('/api/user/speedtest/upload', {
            method: 'POST',
            body: payload,
            cache: 'no-store',
            signal,
          });
          if (resp && resp.ok) {
            totalSentBytes += payload.byteLength;
          }
        } catch (err) {}
      }
    }

    const totalSec = (performance.now() - testStartTime) / 1000;
    const finalUploadMbps = totalSec > 0 && totalSentBytes > 0
      ? (totalSentBytes * 8) / (totalSec * 1000000)
      : 0;

    targetSpeedMbps = finalUploadMbps;
    if (uploadVal) {
      uploadVal.innerText = finalUploadMbps < 10 ? finalUploadMbps.toFixed(1) : Math.round(finalUploadMbps).toString();
    }
    return finalUploadMbps;
  }

  function getVerdictText(dlSpeed, ulSpeed, ping, totalBytes) {
    if (totalBytes === 0) {
      return {
        text: '⚠️ سرورهای تست پاسخ ندادند؛ لطفاً وضعیت اتصال فیلترشکن را بررسی فرمایید.',
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
      // Step 1: Detect Network telemetry & engine source
      const source = await detectEngineAndNetwork(abortController.signal);

      // Step 2: Ping & Jitter Latency
      const { avgPing, jitter } = await measurePingAndJitter(source, abortController.signal);

      // Step 3: Sustained Download Throughput
      const { finalDownloadMbps, totalReceivedBytes } = await measureDownloadThroughput(source, abortController.signal);

      // Step 4: Sustained Upload Throughput
      let finalUploadMbps = 0;
      if (!abortController.signal.aborted) {
        finalUploadMbps = await measureUploadThroughput(source, abortController.signal);
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

/**
 * RemnaStore Pro - Professional Speed & Network Quality Engine
 * Production-grade measurement matching global standards:
 * - RFC 3550 standard Jitter + true Median Latency
 * - Sliding window + Exponential Moving Average (EMA) smoothed throughput (prevents false packet-batch bursts)
 * - Non-compressible cryptographically random upload buffers
 * - Final result summary modal
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

  const domCache = new Map();
  function getEl(id) {
    let el = domCache.get(id);
    if (!el || !el.isConnected) {
      el = document.getElementById(id);
      if (el) domCache.set(id, el);
    }
    return el;
  }

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

  let needleEl = null;
  let speedDisplayEl = null;
  let gaugeProgressArcEl = null;

  function updateGaugeVisual(mbps) {
    if (!needleEl || !needleEl.isConnected) needleEl = getEl('speedGaugeNeedle');
    if (!speedDisplayEl || !speedDisplayEl.isConnected) speedDisplayEl = getEl('speedDisplayVal');
    if (!gaugeProgressArcEl || !gaugeProgressArcEl.isConnected) gaugeProgressArcEl = getEl('speedGaugeProgressArc');

    const angle = speedToAngle(mbps);
    if (needleEl) {
      needleEl.setAttribute('transform', `rotate(${angle}, 100, 100)`);
    }

    if (speedDisplayEl) {
      speedDisplayEl.innerText = mbps < 10 ? mbps.toFixed(1) : Math.round(mbps).toString();
    }

    if (gaugeProgressArcEl) {
      const totalLen = 314.16;
      const angleFraction = (angle - MIN_ANGLE) / TOTAL_DEGREES;
      const offset = totalLen * (1 - Math.max(0, Math.min(1, angleFraction)));
      gaugeProgressArcEl.style.strokeDashoffset = offset.toFixed(2);
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
    return {
      'X-Telegram-Init-Data': window.api ? window.api.getInitData() : '',
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
   * Detect client public IP.
   */
  async function detectEngineAndNetwork(signal) {
    const userIpEl = getEl('speedUserIp');

    // 1. Primary: Server ping probe (instant, reliable, works inside Iran without VPN)
    try {
      let pingData = null;
      if (window.api && typeof window.api.get === 'function') {
        pingData = await window.api.get(`/api/user/speedtest/ping?_t=${Date.now()}`);
      } else if (window.api && typeof window.api.request === 'function') {
        const res = await window.api.request(`/api/user/speedtest/ping?_t=${Date.now()}`, {
          method: 'GET',
          cache: 'no-store',
          signal,
        });
        pingData = res?.data || res;
      }
      const detectedIp = pingData?.ip || pingData?.data?.ip;
      const detectedIsp = pingData?.isp || pingData?.data?.isp;
      if (detectedIp && userIpEl) {
        userIpEl.innerText = detectedIp;
        if (detectedIsp) userIpEl.title = detectedIsp;
        return;
      }
    } catch (e) {}

    // 2. Fallback: Client-side IP detection via ipwho.is
    try {
      const resp = await fetch('https://ipwho.is/', {
        method: 'GET',
        cache: 'no-store',
        signal,
      });
      if (resp && resp.ok) {
        const data = await resp.json();
        if (data && data.success && data.ip && userIpEl) {
          userIpEl.innerText = data.ip;
          return;
        }
      }
    } catch (e) {}
  }

  /**
   * Measure Latency and Jitter with sequential probes.
   * Reports standard Median Ping and RFC 3550 Mean Absolute Deviation Jitter.
   */
  async function measurePingAndJitter(signal) {
    const statusText = getEl('speedStatusBadge');
    const phaseLabel = getEl('speedPhaseLabel');

    if (phaseLabel) phaseLabel.innerText = 'سنجش پینگ و تاخیر...';
    if (statusText) {
      statusText.innerText = '📶 در حال اندازه‌گیری دقیق تاخیر زمانی (Ping)...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-[11px] text-cyan-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    const pings = [];
    const probeCount = 7;

    for (let i = 0; i < probeCount; i++) {
      if (signal && signal.aborted) return { medianPing: 0, jitter: 0 };
      const start = performance.now();
      try {
        const pingUrl = `https://speed.cloudflare.com/__down?bytes=0&_t=${Date.now()}_${i}`;
        let resp = null;
        try {
          resp = await fetch(pingUrl, { method: 'GET', cache: 'no-store', signal });
        } catch (err) {
          resp = await fetch(`/api/user/speedtest/ping?_t=${Date.now()}_${i}`, {
            method: 'GET',
            cache: 'no-store',
            headers: getAuthHeaders(),
            signal,
          });
        }

        if (resp && resp.ok) {
          const duration = performance.now() - start;
          pings.push(duration);
          const pingEl = getEl('speedPingVal');
          if (pingEl) pingEl.innerText = Math.round(duration).toString();
        }
      } catch (e) {}
      await new Promise(r => setTimeout(r, 40));
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

    const pingEl = getEl('speedPingVal');
    const jitterEl = getEl('speedJitterVal');
    if (pingEl) pingEl.innerText = medianPing.toString();
    if (jitterEl) jitterEl.innerText = jitter.toString();

    return { medianPing, jitter };
  }

  /**
   * Helper to stream a download chunk without buffering into mobile RAM.
   */
  async function streamDownload(url, onBytes, signal, timeLimitMs, startTime) {
    try {
      const headers = url.startsWith('/') ? getAuthHeaders() : {};
      const resp = await fetch(url, {
        method: 'GET',
        cache: 'no-store',
        headers,
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
   * Measure Download Throughput with sliding window & EMA smoothing.
   * Prevents false packet clump spikes while remaining accurate.
   */
  async function measureDownloadThroughput(signal) {
    const statusText = getEl('speedStatusBadge');
    const phaseLabel = getEl('speedPhaseLabel');
    const downloadVal = getEl('speedDownloadVal');
    const dataUsedEl = getEl('speedDataUsed');

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
    let smoothedSpeedMbps = 0;

    function onChunk(bytes) {
      totalReceivedBytes += bytes;
      const curTime = performance.now();

      // Warmup: wait 500ms for TCP handshake & slow-start before steady state
      if (curTime - testStartTime > 500 && steadyStartTime === 0) {
        steadyStartTime = curTime;
        steadyStartBytes = totalReceivedBytes;
        lastSampleTime = curTime;
        lastSampleBytes = totalReceivedBytes;
      }

      // Smooth window: sample every 400ms to eliminate TCP ACK clump jitter
      const deltaSec = (curTime - lastSampleTime) / 1000;
      if (deltaSec >= 0.40) {
        const deltaBytes = totalReceivedBytes - lastSampleBytes;
        const instantMbps = (deltaBytes * 8) / (deltaSec * 1000000);

        if (steadyStartTime > 0) {
          samples.push(instantMbps);
          // Exponential moving average: 70% previous + 30% instant
          smoothedSpeedMbps = smoothedSpeedMbps <= 0 ? instantMbps : (smoothedSpeedMbps * 0.70 + instantMbps * 0.30);
          targetSpeedMbps = smoothedSpeedMbps;
        } else {
          targetSpeedMbps = instantMbps;
        }

        lastSampleTime = curTime;
        lastSampleBytes = totalReceivedBytes;
      }

      if (dataUsedEl) {
        dataUsedEl.innerText = (totalReceivedBytes / (1024 * 1024)).toFixed(1);
      }
    }

    async function downloadStreamWithFallback(bytes, nonce, onChunk, signal, limitMs, startTime) {
      const cfUrl = `https://speed.cloudflare.com/__down?bytes=${bytes}&_t=${Date.now()}_${nonce}`;
      let gotData = false;
      try {
        await streamDownload(cfUrl, (b) => { gotData = true; onChunk(b); }, signal, limitMs, startTime);
      } catch (e) {}
      if (!gotData && (!signal || !signal.aborted)) {
        const localUrl = `/api/user/speedtest/payload?bytes=${bytes}&_t=${Date.now()}_${nonce}`;
        await streamDownload(localUrl, onChunk, signal, limitMs, startTime);
      }
    }

    // Step 1: Ramp-up probe (1.5MB)
    await downloadStreamWithFallback(1572864, 'probe', onChunk, signal, 1500, testStartTime);

    // Step 2: Main measurement payload (10MB)
    const remainingTimeMs = Math.max(1000, DOWNLOAD_DURATION_MS - (performance.now() - testStartTime));
    await downloadStreamWithFallback(10485760, 'main', onChunk, signal, remainingTimeMs, testStartTime);

    // Precise steady-state bandwidth: total steady bytes / steady duration
    let finalDownloadMbps = 0;
    if (steadyStartTime > 0 && totalReceivedBytes > steadyStartBytes) {
      const steadyDurationSec = (performance.now() - steadyStartTime) / 1000;
      const steadyBytes = totalReceivedBytes - steadyStartBytes;
      if (steadyDurationSec >= 0.5) {
        finalDownloadMbps = (steadyBytes * 8) / (steadyDurationSec * 1000000);
      }
    }

    // Fallback if steady window wasn't captured
    if (!finalDownloadMbps || finalDownloadMbps <= 0) {
      if (samples.length >= 3) {
        const sorted = [...samples].sort((a, b) => a - b);
        const trimmed = sorted.slice(1, sorted.length - 1);
        finalDownloadMbps = trimmed.reduce((a, b) => a + b, 0) / trimmed.length;
      } else {
        const totalSec = (performance.now() - testStartTime) / 1000;
        finalDownloadMbps = totalSec > 0 ? (totalReceivedBytes * 8) / (totalSec * 1000000) : 0;
      }
    }

    targetSpeedMbps = finalDownloadMbps;
    if (downloadVal) {
      downloadVal.innerText = finalDownloadMbps < 10 ? finalDownloadMbps.toFixed(1) : Math.round(finalDownloadMbps).toString();
    }
    return { finalDownloadMbps, totalReceivedBytes };
  }

  /**
   * Measure Upload Throughput using parallel non-compressible buffers.
   */
  async function measureUploadThroughput(initialReceivedBytes, signal) {
    const statusText = getEl('speedStatusBadge');
    const phaseLabel = getEl('speedPhaseLabel');
    const uploadVal = getEl('speedUploadVal');

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
    let smoothedUploadMbps = 0;

    const randomBuffer = createRandomBuffer(131072); // 128KB for agile non-blocking throughput
    const activeXhrs = new Set();

    const uploadHardTimeout = setTimeout(() => {
      activeXhrs.forEach(xhr => {
        try { xhr.abort(); } catch (e) {}
      });
      activeXhrs.clear();
    }, UPLOAD_DURATION_MS + 200);

    if (signal) {
      signal.addEventListener('abort', () => {
        clearTimeout(uploadHardTimeout);
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

        const endpoint = `/api/user/speedtest/upload?_t=${Date.now()}`;
        xhr.open('POST', endpoint, true);
        xhr.timeout = 2500; // 2.5s timeout per chunk to avoid hanging

        const authHeaders = getAuthHeaders();
        for (const [k, v] of Object.entries(authHeaders)) {
          xhr.setRequestHeader(k, v);
        }
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');

        let lastLoaded = 0;
        let lastTime = performance.now();

        xhr.upload.onprogress = function (e) {
          if (e.loaded > lastLoaded) {
            const now = performance.now();
            const deltaSec = (now - lastTime) / 1000;
            if (deltaSec >= 0.20) {
              const deltaBytes = e.loaded - lastLoaded;
              const instantMbps = (deltaBytes * 8) / (deltaSec * 1000000);
              uploadSamples.push(instantMbps);

              smoothedUploadMbps = smoothedUploadMbps <= 0 ? instantMbps : (smoothedUploadMbps * 0.70 + instantMbps * 0.30);
              targetSpeedMbps = smoothedUploadMbps;

              lastLoaded = e.loaded;
              lastTime = now;
            }
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

        xhr.ontimeout = function () {
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

    // Parallel upload loop with strict duration limit
    while (performance.now() - testStartTime < UPLOAD_DURATION_MS) {
      if (signal && signal.aborted) break;

      const workers = [runUploadWorker(randomBuffer), runUploadWorker(randomBuffer)];
      const results = await Promise.all(workers);
      totalUploadedBytes += (results[0] || 0) + (results[1] || 0);

      if ((results[0] === 0 && results[1] === 0) || (signal && signal.aborted)) break;
      if (performance.now() - testStartTime >= UPLOAD_DURATION_MS) break;
    }
    clearTimeout(uploadHardTimeout);

    let finalUploadMbps = 0;
    if (uploadSamples.length >= 3) {
      const sorted = [...uploadSamples].sort((a, b) => a - b);
      const trimCount = Math.max(1, Math.floor(sorted.length * 0.15));
      const trimmed = sorted.slice(trimCount, sorted.length - trimCount);
      finalUploadMbps = trimmed.reduce((a, b) => a + b, 0) / trimmed.length;
    }
    if ((!finalUploadMbps || finalUploadMbps <= 0) && totalUploadedBytes > 0) {
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
        rating: '❌ قطع ارتباط',
      };
    }
    if (dlSpeed >= 25 && ping <= 90) {
      return {
        text: '🚀 کیفیت فوق‌العاده؛ عالی برای استریم 4K، بازی آنلاین و وب‌گردی پرسرعت',
        cls: 'bg-emerald-950/70 border-emerald-500/50 text-emerald-300',
        rating: '🚀 فوق‌العاده',
      };
    }
    if (dlSpeed >= 12) {
      return {
        text: '⚡️ کیفیت بسیار خوب؛ عالی برای اینستاگرام، تلگرام، یوتیوب HD و تماس ویدیویی',
        cls: 'bg-cyan-950/70 border-cyan-500/50 text-cyan-300',
        rating: '⚡️ بسیار خوب',
      };
    }
    if (dlSpeed >= 4) {
      return {
        text: '🟡 کیفیت معمولی؛ مناسب برای چت، وب‌گردی و دانلود با سرعت استاندارد',
        cls: 'bg-amber-950/70 border-amber-500/50 text-amber-300',
        rating: '📶 معمولی',
      };
    }
    return {
      text: '⚠️ سرعت محدود؛ مناسب برای ارسال پیام متنی یا نیازمند تغییر سرور/پروکسی',
      cls: 'bg-rose-950/70 border-rose-500/50 text-rose-300',
      rating: '⚠️ ضعیف',
    };
  }

  function openSpeedResultsModal({ download, upload, ping, jitter, dataUsed, rating }) {
    const modal = getEl('speedResultsModal');
    if (!modal) return;

    const dlEl = getEl('finalDownloadVal');
    const ulEl = getEl('finalUploadVal');
    const pingEl = getEl('finalPingVal');
    const jitterEl = getEl('finalJitterVal');
    const dataEl = getEl('finalDataUsedVal');
    const badgeEl = getEl('speedResultRatingBadge');

    if (dlEl) dlEl.innerText = download < 10 ? download.toFixed(1) : Math.round(download).toString();
    if (ulEl) ulEl.innerText = upload < 10 ? upload.toFixed(1) : Math.round(upload).toString();
    if (pingEl) pingEl.innerText = ping ? Math.round(ping).toString() : '--';
    if (jitterEl) jitterEl.innerText = jitter ? Math.round(jitter).toString() : '--';
    if (dataEl) dataEl.innerText = dataUsed || '0.0';
    if (badgeEl && rating) badgeEl.innerText = rating;

    modal.classList.remove('hidden');
    if (window.hapticFeedback) window.hapticFeedback('success');
  }

  function closeSpeedResultsModal() {
    const modal = getEl('speedResultsModal');
    if (modal) modal.classList.add('hidden');
  }

  async function startSpeedTest() {
    if (isTesting) return;

    const startBtn = getEl('startSpeedTestBtn');
    const statusText = getEl('speedStatusBadge');
    const startBtnText = getEl('startSpeedTestBtnText');
    const phaseLabel = getEl('speedPhaseLabel');
    const downloadVal = getEl('speedDownloadVal');
    const uploadVal = getEl('speedUploadVal');

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

    const dataUsedEl = getEl('speedDataUsed');
    if (dataUsedEl) dataUsedEl.innerText = '0.0';

    if (window.hapticFeedback) window.hapticFeedback('impact');

    try {
      // Step 1: Detect Network IP
      await detectEngineAndNetwork(abortController.signal);

      // Step 2: Ping & Jitter Latency (RFC 3550 & Median Ping)
      const { medianPing, jitter } = await measurePingAndJitter(abortController.signal);

      // Step 3: Sustained Download Throughput (Sliding Window & EMA Smoothed)
      const { finalDownloadMbps, totalReceivedBytes } = await measureDownloadThroughput(abortController.signal);

      // Step 4: Sustained Upload Throughput (Non-compressible buffers)
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

      // Step 6: Open summary results modal if test finished without abort
      if (!abortController.signal.aborted) {
        setTimeout(() => {
          openSpeedResultsModal({
            download: finalDownloadMbps,
            upload: finalUploadMbps,
            ping: medianPing,
            jitter: jitter,
            dataUsed: (totalReceivedBytes / (1024 * 1024)).toFixed(1),
            rating: verdict.rating,
          });
        }, 350);
      }
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

    const startBtn = getEl('startSpeedTestBtn');
    const startBtnText = getEl('startSpeedTestBtnText');
    const statusText = getEl('speedStatusBadge');
    const phaseLabel = getEl('speedPhaseLabel');

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
    const modal = getEl('speedTestModal');
    if (modal) {
      const isLight = document.documentElement.classList.contains('theme-light');
      modal.style.backgroundColor = isLight ? 'rgba(15, 23, 42, 0.45)' : 'rgba(0, 0, 0, 0.8)';
    }

    if (window.openModal) {
      window.openModal('speedTestModal');
    } else {
      getEl('speedTestModal')?.classList.remove('hidden');
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
      getEl('speedTestModal')?.classList.add('hidden');
    }
    if (window.syncTelegramBackButton) window.syncTelegramBackButton();
    if (window.hapticFeedback) window.hapticFeedback('selection');
  }

  window.openSpeedTestModal = openSpeedTestModal;
  window.closeSpeedTestModal = closeSpeedTestModal;
  window.openSpeedResultsModal = openSpeedResultsModal;
  window.closeSpeedResultsModal = closeSpeedResultsModal;
  window.startSpeedTest = startSpeedTest;
  window.stopSpeedTest = stopSpeedTest;
  window.toggleSpeedTest = toggleSpeedTest;
})();

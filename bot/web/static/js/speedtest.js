/**
 * RemnaStore Pro - Bulletproof Client-Side Speed & Ping Test Engine
 * Measures true user latency, jitter, and real-time streaming download throughput.
 * Uses global Cloudflare Speed CDN with automatic seamless bot-server fallback.
 */

(function () {
  let isTesting = false;
  let abortController = null;
  let animationFrameId = null;
  let currentSpeedMbps = 0;
  let targetSpeedMbps = 0;
  let lastToggleTime = 0;

  // Gauge geometry configuration (-210 deg to 30 deg = 240 deg sweep)
  const MIN_ANGLE = -210;
  const MAX_ANGLE = 30;
  const TOTAL_DEGREES = 240;
  const MAX_GAUGE_MBPS = 100;
  const TEST_DURATION_MS = 5500; // 5.5-second realistic measurement cycle

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
    if (!isTesting && Math.abs(currentSpeedMbps - targetSpeedMbps) < 0.1) {
      currentSpeedMbps = targetSpeedMbps;
      updateGaugeVisual(currentSpeedMbps);
      return;
    }

    currentSpeedMbps += (targetSpeedMbps - currentSpeedMbps) * 0.18;
    updateGaugeVisual(currentSpeedMbps);
    animationFrameId = requestAnimationFrame(animateGauge);
  }

  /**
   * Determine best speedtest engine source:
   * Cloudflare Speed CDN (global edge) vs local bot server fallback.
   */
  async function detectBestSource(signal) {
    const serverBadge = document.getElementById('speedServerBadge');
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
        if (serverBadge) {
          serverBadge.innerText = '🌐 سرور تست: Cloudflare CDN (جهانی)';
          serverBadge.className = 'text-[9px] bg-cyan-950/70 border border-cyan-500/40 text-cyan-300 px-2 py-0.5 rounded-full font-medium';
        }
        return 'cloudflare';
      }
    } catch (e) {
      // Cloudflare unreachable or filtered -> fallback to bot server
    }

    if (serverBadge) {
      serverBadge.innerText = '⚡️ سرور تست: سرور اختصاصی ربات';
      serverBadge.className = 'text-[9px] bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 px-2 py-0.5 rounded-full font-medium';
    }
    return 'server';
  }

  /**
   * Measure Ping (RTT) and Jitter with sequential probes.
   */
  async function measurePingAndJitter(source, signal) {
    const statusText = document.getElementById('speedStatusBadge');
    if (statusText) {
      statusText.innerText = '📶 در حال سنجش پینگ و تاخیر شبکه...';
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
      } catch (e) {
        // Ignore single ping failure
      }
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
   * Continuous multi-chunk streaming download throughput measurement.
   * Resilient against WebView limitations and network interruptions.
   */
  async function measureDownloadThroughput(initialSource, signal) {
    const statusText = document.getElementById('speedStatusBadge');
    if (statusText) {
      statusText.innerText = '⚡️ در حال دریافت داده و سنجش سرعت دانلود...';
      statusText.className = 'py-1.5 px-3 rounded-xl bg-blue-950/60 border border-blue-500/40 text-[11px] text-blue-300 font-medium transition text-center min-h-[38px] flex items-center justify-center';
    }

    let activeSource = initialSource;
    const testStartTime = performance.now();
    let totalReceivedBytes = 0;
    const speedSamples = [];

    // Progressive chunk sequence: 512KB -> 1MB -> 2MB -> 4MB -> 8MB
    const chunkSizes = [524288, 1048576, 2097152, 4194304, 8388608];
    let chunkIndex = 0;

    let lastSampleTime = testStartTime;
    let lastSampleBytes = 0;

    while (performance.now() - testStartTime < TEST_DURATION_MS) {
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

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        // Support both ReadableStream streaming and ArrayBuffer fallback for all mobile WebViews
        if (response.body && typeof response.body.getReader === 'function') {
          const reader = response.body.getReader();

          while (true) {
            if (performance.now() - testStartTime >= TEST_DURATION_MS || (signal && signal.aborted)) {
              try { reader.cancel(); } catch (e) {}
              break;
            }

            const { done, value } = await reader.read();
            if (done) break;

            if (value && value.length > 0) {
              totalReceivedBytes += value.length;
              const now = performance.now();
              const deltaSec = (now - lastSampleTime) / 1000;

              if (deltaSec >= 0.1) {
                const deltaBytes = totalReceivedBytes - lastSampleBytes;
                const instantMbps = (deltaBytes * 8) / (deltaSec * 1000000);

                if (now - testStartTime > 250) {
                  speedSamples.push(instantMbps);
                }
                targetSpeedMbps = instantMbps;

                lastSampleTime = now;
                lastSampleBytes = totalReceivedBytes;
              }

              const dataUsedEl = document.getElementById('speedDataUsed');
              if (dataUsedEl) {
                dataUsedEl.innerText = `${(totalReceivedBytes / (1024 * 1024)).toFixed(1)} MB`;
              }
            }
          }
        } else {
          // Fallback for WebViews without full ReadableStream support
          const buf = await response.arrayBuffer();
          if (buf && buf.byteLength > 0) {
            totalReceivedBytes += buf.byteLength;
            const now = performance.now();
            const deltaSec = (now - lastSampleTime) / 1000;
            if (deltaSec > 0.05) {
              const deltaBytes = totalReceivedBytes - lastSampleBytes;
              const instantMbps = (deltaBytes * 8) / (deltaSec * 1000000);
              speedSamples.push(instantMbps);
              targetSpeedMbps = instantMbps;
              lastSampleTime = now;
              lastSampleBytes = totalReceivedBytes;
            }
            const dataUsedEl = document.getElementById('speedDataUsed');
            if (dataUsedEl) {
              dataUsedEl.innerText = `${(totalReceivedBytes / (1024 * 1024)).toFixed(1)} MB`;
            }
          }
        }
      } catch (err) {
        if (signal && signal.aborted) break;

        // If Cloudflare fails mid-test, seamlessly switch to bot server without failing
        if (activeSource === 'cloudflare') {
          activeSource = 'server';
          const serverBadge = document.getElementById('speedServerBadge');
          if (serverBadge) {
            serverBadge.innerText = '⚡️ سرور تست: سرور اختصاصی ربات (فال‌بک)';
            serverBadge.className = 'text-[9px] bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 px-2 py-0.5 rounded-full font-medium';
          }
          await new Promise(r => setTimeout(r, 100));
          continue;
        }
        break;
      }
    }

    const totalDurationSec = (performance.now() - testStartTime) / 1000;

    let finalThroughputMbps = 0;
    if (speedSamples.length > 0) {
      const sorted = [...speedSamples].sort((a, b) => a - b);
      const p80Index = Math.floor(sorted.length * 0.75);
      finalThroughputMbps = sorted[p80Index];
    } else if (totalDurationSec > 0 && totalReceivedBytes > 0) {
      finalThroughputMbps = (totalReceivedBytes * 8) / (totalDurationSec * 1000000);
    }

    targetSpeedMbps = finalThroughputMbps;
    return { finalMbps: finalThroughputMbps, totalBytes: totalReceivedBytes };
  }

  function getVerdictText(speed, ping, totalBytes) {
    if (totalBytes === 0) {
      return {
        text: '⚠️ سرورهای تست پاسخ ندادند؛ وضعیت اینترنت یا فیلترشکن را بررسی فرمایید.',
        cls: 'bg-amber-950/70 border-amber-500/50 text-amber-300',
      };
    }
    if (speed >= 30 && ping <= 90) {
      return {
        text: '🚀 کیفیت فوق‌العاده؛ عالی برای استریم 4K، بازی آنلاین و وب‌گردی پرسرعت',
        cls: 'bg-emerald-950/70 border-emerald-500/50 text-emerald-300',
      };
    }
    if (speed >= 15) {
      return {
        text: '⚡️ کیفیت بسیار خوب؛ عالی برای اینستاگرام، تلگرام، یوتیوب HD و تماس ویدیویی',
        cls: 'bg-cyan-950/70 border-cyan-500/50 text-cyan-300',
      };
    }
    if (speed >= 5) {
      return {
        text: '🟡 کیفیت معمولی؛ مناسب برای چت، وب‌گردی و ارسال فایل با حجم استاندارد',
        cls: 'bg-amber-950/70 border-amber-500/50 text-amber-300',
      };
    }
    return {
      text: '⚠️ سرعت پایین؛ اتصال ناپایدار یا اختلال شبکه/پروکسی',
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
      startBtn.classList.add('bg-rose-600', 'hover:bg-rose-500');
      startBtn.classList.remove('bg-gradient-to-r', 'from-emerald-500');
    }
    if (startBtnText) startBtnText.innerText = 'توقف تست ⏹️';

    targetSpeedMbps = 0;
    currentSpeedMbps = 0;
    updateGaugeVisual(0);
    animateGauge();

    const dataUsedEl = document.getElementById('speedDataUsed');
    if (dataUsedEl) dataUsedEl.innerText = '0.0 MB';

    if (window.hapticFeedback) window.hapticFeedback('impact');

    try {
      // Step 1: Detect engine source (Cloudflare CDN vs Bot Server)
      const source = await detectBestSource(abortController.signal);

      // Step 2: Ping & Jitter
      const { avgPing, jitter } = await measurePingAndJitter(source, abortController.signal);

      // Step 3: Sustained Download Throughput Streaming
      const { finalMbps, totalBytes } = await measureDownloadThroughput(source, abortController.signal);

      // Step 4: Quality Verdict
      const verdict = getVerdictText(finalMbps, avgPing, totalBytes);
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
          statusText.innerText = '⚠️ اختلال موقت در ارتباط؛ لطفاً مجدداً دکمه شروع را لمس فرمایید.';
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
      if (startBtnText) startBtnText.innerText = 'تست مجدد سرعت 🚀';
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

    if (startBtn) {
      startBtn.classList.remove('bg-rose-600', 'hover:bg-rose-500');
      startBtn.classList.add('bg-gradient-to-r', 'from-emerald-500');
    }
    if (startBtnText) startBtnText.innerText = 'شروع تست سرعت 🚀';
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

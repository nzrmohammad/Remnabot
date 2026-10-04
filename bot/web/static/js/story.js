/**
 * RemnaStore Pro - Story Cards & Viral Sharing Generator
 */

let currentStoryTheme = 'glass';

function applyStoryTheme(theme) {
  currentStoryTheme = theme;
  const presetThemeGlassBtn = document.getElementById('presetThemeGlassBtn');
  const presetThemeCyberBtn = document.getElementById('presetThemeCyberBtn');
  const presetThemeSpeedBtn = document.getElementById('presetThemeSpeedBtn');
  const exportableStoryCard = document.getElementById('exportableStoryCard');
  const storyGlow1 = document.getElementById('storyGlow1');
  const storyGlow2 = document.getElementById('storyGlow2');
  const storyBrandIcon = document.getElementById('storyBrandIcon');
  const storyBrandTitle = document.getElementById('storyBrandTitle');
  const storyBrandBadge = document.getElementById('storyBrandBadge');
  const storyMetricsStandard = document.getElementById('storyMetricsStandard');
  const storyMetricsSpeed = document.getElementById('storyMetricsSpeed');
  const storyAvatarBorder = document.getElementById('storyAvatarBorder');

  const allBtns = [presetThemeGlassBtn, presetThemeCyberBtn, presetThemeSpeedBtn];
  allBtns.forEach(b => {
    b?.classList.remove('active', 'border-indigo-400/80', 'bg-indigo-600/30', 'text-indigo-200', 'border-emerald-400/80', 'bg-emerald-600/30', 'text-emerald-200', 'border-cyan-400/80', 'bg-cyan-600/30', 'text-cyan-200');
    b?.classList.add('border-slate-700', 'bg-slate-800/80', 'text-slate-300');
  });

  if (theme === 'glass') {
    presetThemeGlassBtn?.classList.add('active', 'border-indigo-400/80', 'bg-indigo-600/30', 'text-indigo-200');
    presetThemeGlassBtn?.classList.remove('border-slate-700', 'bg-slate-800/80', 'text-slate-300');
    if (exportableStoryCard) {
      exportableStoryCard.style.background = 'linear-gradient(135deg, rgba(30, 27, 75, 0.9) 0%, rgba(15, 23, 42, 0.96) 50%, rgba(49, 46, 129, 0.85) 100%)';
      exportableStoryCard.style.borderColor = 'rgba(255, 255, 255, 0.2)';
      exportableStoryCard.style.boxShadow = '0 20px 50px rgba(0, 0, 0, 0.8)';
    }
    if (storyGlow1) storyGlow1.className = 'absolute -top-12 -right-12 w-32 h-32 bg-cyan-500/20 rounded-full blur-2xl pointer-events-none transition-all duration-500';
    if (storyGlow2) storyGlow2.className = 'absolute -bottom-12 -left-12 w-32 h-32 bg-purple-500/25 rounded-full blur-2xl pointer-events-none transition-all duration-500';
    if (storyBrandIcon) storyBrandIcon.innerText = '⚡️';
    if (storyBrandTitle) {
      storyBrandTitle.innerText = 'RemnaStore Pro';
      storyBrandTitle.className = 'font-extrabold text-xs text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-blue-300 to-indigo-300';
    }
    if (storyBrandBadge) {
      storyBrandBadge.innerText = 'VIP MEMBER';
      storyBrandBadge.className = 'text-[9px] font-mono font-bold text-amber-300 bg-amber-950/60 border border-amber-500/30 px-2 py-0.5 rounded-full';
    }
    if (storyAvatarBorder) storyAvatarBorder.className = 'w-12 h-12 rounded-full p-0.5 bg-gradient-to-tr from-cyan-400 to-indigo-500 mx-auto shadow-lg shadow-indigo-500/30 flex items-center justify-center transition-all duration-300';
    storyMetricsStandard?.classList.remove('hidden');
    storyMetricsSpeed?.classList.add('hidden');
  } else if (theme === 'cyber') {
    presetThemeCyberBtn?.classList.add('active', 'border-emerald-400/80', 'bg-emerald-600/30', 'text-emerald-200');
    presetThemeCyberBtn?.classList.remove('border-slate-700', 'bg-slate-800/80', 'text-slate-300');
    if (exportableStoryCard) {
      exportableStoryCard.style.background = '#060913';
      exportableStoryCard.style.borderColor = 'rgba(16, 185, 129, 0.7)';
      exportableStoryCard.style.boxShadow = '0 0 35px rgba(16, 185, 129, 0.25)';
    }
    if (storyGlow1) storyGlow1.className = 'absolute -top-12 -right-12 w-32 h-32 bg-emerald-500/25 rounded-full blur-2xl pointer-events-none transition-all duration-500';
    if (storyGlow2) storyGlow2.className = 'absolute -bottom-12 -left-12 w-32 h-32 bg-teal-500/20 rounded-full blur-2xl pointer-events-none transition-all duration-500';
    if (storyBrandIcon) storyBrandIcon.innerText = '👾';
    if (storyBrandTitle) {
      storyBrandTitle.innerText = 'REMNA CYBERNET';
      storyBrandTitle.className = 'font-black text-xs text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 font-mono tracking-wide';
    }
    if (storyBrandBadge) {
      storyBrandBadge.innerText = '⚡️ LOW PING';
      storyBrandBadge.className = 'text-[9px] font-mono font-bold text-emerald-300 bg-emerald-950/80 border border-emerald-500/40 px-2 py-0.5 rounded-full';
    }
    if (storyAvatarBorder) storyAvatarBorder.className = 'w-12 h-12 rounded-full p-0.5 bg-gradient-to-tr from-emerald-400 to-teal-300 mx-auto shadow-lg shadow-emerald-500/40 flex items-center justify-center transition-all duration-300';
    storyMetricsStandard?.classList.remove('hidden');
    storyMetricsSpeed?.classList.add('hidden');
  } else if (theme === 'speed') {
    presetThemeSpeedBtn?.classList.add('active', 'border-cyan-400/80', 'bg-cyan-600/30', 'text-cyan-200');
    presetThemeSpeedBtn?.classList.remove('border-slate-700', 'bg-slate-800/80', 'text-slate-300');
    if (exportableStoryCard) {
      exportableStoryCard.style.background = 'linear-gradient(135deg, #071026 0%, #0d224a 50%, #071026 100%)';
      exportableStoryCard.style.borderColor = 'rgba(6, 182, 212, 0.7)';
      exportableStoryCard.style.boxShadow = '0 0 35px rgba(6, 182, 212, 0.25)';
    }
    if (storyGlow1) storyGlow1.className = 'absolute -top-12 -right-12 w-32 h-32 bg-cyan-500/30 rounded-full blur-2xl pointer-events-none transition-all duration-500';
    if (storyGlow2) storyGlow2.className = 'absolute -bottom-12 -left-12 w-32 h-32 bg-blue-500/25 rounded-full blur-2xl pointer-events-none transition-all duration-500';
    if (storyBrandIcon) storyBrandIcon.innerText = '🚀';
    if (storyBrandTitle) {
      storyBrandTitle.innerText = 'SPEED & BENCHMARK';
      storyBrandTitle.className = 'font-black text-xs text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-sky-300 to-blue-400 font-mono tracking-wide';
    }
    if (storyBrandBadge) {
      storyBrandBadge.innerText = '🟢 100% ONLINE';
      storyBrandBadge.className = 'text-[9px] font-mono font-bold text-cyan-300 bg-cyan-950/80 border border-cyan-500/40 px-2 py-0.5 rounded-full';
    }
    if (storyAvatarBorder) storyAvatarBorder.className = 'w-12 h-12 rounded-full p-0.5 bg-gradient-to-tr from-cyan-400 to-blue-500 mx-auto shadow-lg shadow-cyan-500/40 flex items-center justify-center transition-all duration-300';
    storyMetricsStandard?.classList.add('hidden');
    storyMetricsSpeed?.classList.remove('hidden');
  }
}

function setupStoryCard() {
  const openStoryCardBtn = document.getElementById('openStoryCardBtn');
  const closeStoryCardBtn = document.getElementById('closeStoryCardBtn');
  const downloadStoryBtn = document.getElementById('downloadStoryBtn');
  const shareTelegramStoryBtn = document.getElementById('shareTelegramStoryBtn');

  openStoryCardBtn?.addEventListener('click', () => openModal('storyCardModal'));
  closeStoryCardBtn?.addEventListener('click', () => closeModal('storyCardModal'));

  document.getElementById('presetThemeGlassBtn')?.addEventListener('click', () => applyStoryTheme('glass'));
  document.getElementById('presetThemeCyberBtn')?.addEventListener('click', () => applyStoryTheme('cyber'));
  document.getElementById('presetThemeSpeedBtn')?.addEventListener('click', () => applyStoryTheme('speed'));

  shareTelegramStoryBtn?.addEventListener('click', () => {
    const refLink = window.currentReferralLink || `https://t.me/RemnaWaveBot?start=ref_${window.lastUserData?.user?.id || ''}`;
    copyToClipboard(refLink);

    let sharedViaStory = false;
    const qrEl = document.getElementById('storyCardQr');
    const mediaUrl = qrEl?.src || '';
    if (window.Telegram?.WebApp?.shareToStory && mediaUrl) {
      try {
        window.Telegram.WebApp.shareToStory(mediaUrl, {
          text: '🚀 اتصال پرسرعت به اینترنت بدون قطعی\n🎁 با این کارت ۱ گیگابایت هدیه رایگان بگیرید!',
          widget_link: {
            url: refLink,
            name: 'دریافت اینترنت هدیه'
          }
        });
        sharedViaStory = true;
      } catch(e) {
        sharedViaStory = false;
      }
    }

    if (!sharedViaStory) {
      const shareMsg = '🚀 اتصال فوق‌سریع و بدون قطعی به اینترنت آزاد\n🎁 با لینک دعوت اختصاصی من ۱ گیگابایت اینترنت هدیه بگیرید:\n' + refLink;
      const tgShareUrl = `https://t.me/share/url?url=${encodeURIComponent(refLink)}&text=${encodeURIComponent(shareMsg)}`;
      if (window.Telegram?.WebApp?.openTelegramLink) {
        try { window.Telegram.WebApp.openTelegramLink(tgShareUrl); } catch(e) { window.open(tgShareUrl, '_blank'); }
      } else {
        window.open(tgShareUrl, '_blank');
      }
    }
    showToast('🚀 لینک دعوت کپی شد و صفحه اشتراک‌گذاری در استوری باز گردید.');
  });

  downloadStoryBtn?.addEventListener('click', () => {
    const canvas = document.createElement('canvas');
    canvas.width = 600;
    canvas.height = 780;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      showToast('⚠️ مرورگر شما از ایجاد تصویر پشتیبانی نمی‌کند.');
      return;
    }

    if (currentStoryTheme === 'cyber') {
      ctx.fillStyle = '#060913';
      ctx.fillRect(0, 0, 600, 780);
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 6;
      ctx.strokeRect(15, 15, 570, 750);
    } else if (currentStoryTheme === 'speed') {
      const grad = ctx.createLinearGradient(0, 0, 600, 780);
      grad.addColorStop(0, '#071026');
      grad.addColorStop(0.5, '#0d224a');
      grad.addColorStop(1, '#071026');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 600, 780);
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 6;
      ctx.strokeRect(15, 15, 570, 750);
    } else {
      const grad = ctx.createLinearGradient(0, 0, 600, 780);
      grad.addColorStop(0, '#1e1b4b');
      grad.addColorStop(0.5, '#0f172a');
      grad.addColorStop(1, '#312e81');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 600, 780);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.lineWidth = 4;
      ctx.strokeRect(15, 15, 570, 750);
    }

    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 28px Vazirmatn, sans-serif';
    const title = currentStoryTheme === 'cyber' ? 'REMNA CYBERNET' : (currentStoryTheme === 'speed' ? 'SPEED & BENCHMARK' : 'RemnaStore Pro');
    ctx.fillText(title, 300, 75);

    ctx.beginPath();
    ctx.arc(300, 160, 45, 0, Math.PI * 2);
    ctx.fillStyle = currentStoryTheme === 'cyber' ? '#10b981' : (currentStoryTheme === 'speed' ? '#06b6d4' : '#6366f1');
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 36px Vazirmatn, sans-serif';
    const initial = (document.getElementById('storyCardAvatarInitial')?.innerText || 'U').trim();
    ctx.fillText(initial, 300, 172);

    const sName = (document.getElementById('storyCardName')?.innerText || 'کاربر').trim();
    const sUser = (document.getElementById('storyCardUsername')?.innerText || '').trim();
    ctx.font = 'bold 24px Vazirmatn, sans-serif';
    ctx.fillText(sName, 300, 240);
    ctx.font = '16px monospace';
    ctx.fillStyle = '#93c5fd';
    ctx.fillText(sUser, 300, 268);

    ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
    ctx.fillRect(60, 300, 480, 180);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.strokeRect(60, 300, 480, 180);

    if (currentStoryTheme === 'speed') {
      ctx.font = 'bold 22px Vazirmatn, sans-serif';
      ctx.fillStyle = '#38bdf8';
      ctx.fillText('⚡️ پینگ زنده سرورها: ۳۲ میلی‌ثانیه', 300, 345);
      ctx.font = '18px monospace';
      ctx.fillStyle = '#34d399';
      ctx.fillText('🇩🇪 DE: 32ms    •    🇳🇱 NL: 38ms', 300, 395);
      ctx.font = '16px Vazirmatn, sans-serif';
      ctx.fillStyle = '#10b981';
      ctx.fillText('🟢 ۱۰۰٪ آنلاین و بدون افت سرعت', 300, 445);
    } else {
      ctx.font = '16px Vazirmatn, sans-serif';
      ctx.fillStyle = '#cbd5e1';
      ctx.fillText('ترافیک باقی‌مانده اشتراک:', 300, 340);
      ctx.font = 'bold 44px monospace';
      ctx.fillStyle = '#34d399';
      const sTraf = (document.getElementById('storyCardTraffic')?.innerText || '-- GB').trim();
      ctx.fillText(sTraf, 300, 400);
      ctx.font = '16px Vazirmatn, sans-serif';
      ctx.fillStyle = '#cbd5e1';
      const sDays = (document.getElementById('storyCardDays')?.innerText || '-- روز').trim();
      ctx.fillText(`${sDays}  •  🌍 کلاستر اختصاصی`, 300, 445);
    }

    ctx.font = 'bold 22px Vazirmatn, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.fillText('اینترنت بدون قطعی و پرسرعت', 300, 525);
    ctx.font = '18px Vazirmatn, sans-serif';
    ctx.fillStyle = '#34d399';
    ctx.fillText('🎁 با این کارت ۱ گیگابایت هدیه رایگان بگیرید', 300, 560);

    const qrImg = document.getElementById('storyCardQr');
    const finishDownload = () => {
      const link = document.createElement('a');
      link.download = 'remna-story-card.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
      showToast('📸 پوستر استوری با بالاترین کیفیت در گالری ذخیره شد.');
    };

    if (qrImg && qrImg.complete && qrImg.naturalWidth > 0) {
      try { ctx.drawImage(qrImg, 240, 590, 120, 120); } catch(e) {}
      finishDownload();
    } else {
      finishDownload();
    }
  });
}

window.applyStoryTheme = applyStoryTheme;
window.setupStoryCard = setupStoryCard;

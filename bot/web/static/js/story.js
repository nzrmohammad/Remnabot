/**
 * RemnaStore Pro - Story Cards & Viral Sharing Generator
 */

function setupStoryCard() {
  const closeStoryCardBtn = document.getElementById('closeStoryCardBtn');
  const downloadStoryBtn = document.getElementById('downloadStoryBtn');
  const shareTelegramStoryBtn = document.getElementById('shareTelegramStoryBtn');
  const storyModeReferralBtn = document.getElementById('storyModeReferralBtn');
  const storyModeUsageBtn = document.getElementById('storyModeUsageBtn');

  let currentStoryMode = 'referral';

  const updateStoryModeUI = (mode) => {
    currentStoryMode = mode;
    const isUsage = mode === 'usage';
    if (storyModeReferralBtn) {
      storyModeReferralBtn.className = isUsage
        ? 'flex-1 py-1 px-2 text-xs font-medium rounded-lg transition text-slate-300 hover:text-white flex items-center justify-center gap-1 cursor-pointer bg-transparent border-0'
        : 'flex-1 py-1 px-2 text-xs font-bold rounded-lg transition bg-indigo-600 text-white shadow-sm flex items-center justify-center gap-1 cursor-pointer border-0';
    }
    if (storyModeUsageBtn) {
      storyModeUsageBtn.className = isUsage
        ? 'flex-1 py-1 px-2 text-xs font-bold rounded-lg transition bg-indigo-600 text-white shadow-sm flex items-center justify-center gap-1 cursor-pointer border-0'
        : 'flex-1 py-1 px-2 text-xs font-medium rounded-lg transition text-slate-300 hover:text-white flex items-center justify-center gap-1 cursor-pointer bg-transparent border-0';
    }

    const brandTitle = document.getElementById('storyBrandTitle');
    const brandBadge = document.getElementById('storyBrandBadge');
    const gamificationBanner = document.getElementById('storyGamificationBanner');
    const rewardText = document.getElementById('storyCardRewardText');

    if (isUsage) {
      if (brandTitle) brandTitle.innerText = 'کارنامه اینترنت آزاد';
      if (brandBadge) brandBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span> WRAPPED PRO';
      if (gamificationBanner) gamificationBanner.innerHTML = '<span class="font-black block text-cyan-300 mb-0.5">📊 کارنامه مصرف اینترنت آزاد شما:</span>این تصویر آماری خلاصه از مصرف و پایداری اتصال شما را نشان می‌دهد. می‌توانید آن را در استوری تلگرام با دوستانتان به اشتراک بگذارید!';
      if (rewardText) rewardText.innerHTML = '🟢 اتصال پایدار 100% بدون مرز و فیلترینگ';
    } else {
      if (brandTitle) brandTitle.innerText = 'RemnaStore Pro';
      if (brandBadge) brandBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> VIP PASS';
      if (gamificationBanner) gamificationBanner.innerHTML = '<span class="font-black block text-amber-300 mb-0.5"><img src="/static/img/icons/award.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle ml-1" width="16" height="16" alt="" />پاداش استوری و اشتراک‌گذاری:</span>با انتشار این تصویر در استوری تلگرام، دوستانتان عضو شده و پس از اولین خریدشان، <b id="storyRewardBannerGb" class="text-amber-300 font-sans">5</b> گیگابایت پاداش معرف برای شما واریز می‌شود!';
      if (rewardText) {
        const rewardVal = window.lastUserData?.user?.referral_reward_gb ?? (document.getElementById('storyCardRewardGb')?.innerText || '5');
        rewardText.innerHTML = `<img src="/static/img/icons/gift.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle ml-1" width="16" height="16" alt="" />با این کارت <span id="storyCardRewardGb" class="font-sans">${toEnglishDigits(rewardVal)}</span> گیگابایت هدیه بگیرید`;
      }
    }
  };

  storyModeReferralBtn?.addEventListener('click', () => {
    (window.api?.haptic || window.hapticFeedback || hapticFeedback)('selection');
    if (typeof playSubtleSound === 'function') playSubtleSound('light');
    updateStoryModeUI('referral');
  });

  storyModeUsageBtn?.addEventListener('click', () => {
    (window.api?.haptic || window.hapticFeedback || hapticFeedback)('selection');
    if (typeof playSubtleSound === 'function') playSubtleSound('light');
    updateStoryModeUI('usage');
  });

  const storyModal = bindModal('storyCardModal', 'closeStoryCardBtn');
  window.openStoryCard = (mode = 'referral') => {
    (window.api?.haptic || window.hapticFeedback || hapticFeedback)('selection');
    updateStoryModeUI(mode === 'usage' ? 'usage' : 'referral');
    storyModal.open();
  };

  shareTelegramStoryBtn?.addEventListener('click', () => {
    (window.api?.haptic || window.hapticFeedback || hapticFeedback)('light');
    const botUser = window.lastUserData?.bot_username || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || '';
    const fallbackRef = window.buildRefLink(botUser, window.lastUserData?.user?.id);
    const refLink = window.currentReferralLink || fallbackRef;
    copyToClipboard(refLink);

    const isUsage = currentStoryMode === 'usage';
    const rewardVal = window.lastUserData?.user?.referral_reward_gb
      ?? (document.getElementById('storyCardRewardGb')?.innerText || '5');
    const rewardGb = String(rewardVal).trim();
    let sharedViaStory = false;
    const qrEl = document.getElementById('storyCardQr');
    const mediaUrl = qrEl?.src || '';
    if (window.Telegram?.WebApp?.shareToStory && mediaUrl) {
      try {
        const storyCaption = isUsage
          ? '📊 کارنامه اینترنت آزاد و بدون قطعی من در ربات رمنا\n🌐 اتصال پرسرعت بین‌المللی'
          : `🚀 اتصال پرسرعت به اینترنت بدون قطعی\n🎁 با این کارت ${rewardGb} گیگابایت هدیه رایگان بگیرید!`;
        window.Telegram.WebApp.shareToStory(mediaUrl, {
          text: storyCaption,
          widget_link: {
            url: refLink,
            name: isUsage ? 'دریافت اینترنت آزاد' : 'دریافت اینترنت هدیه',
          },
        });
        sharedViaStory = true;
      } catch (e) {
        sharedViaStory = false;
      }
    }

    if (!sharedViaStory) {
      const shareMsg = isUsage
        ? '📊 کارنامه اتصال اینترنت آزاد من در ربات رمنا:\n' + refLink
        : `🚀 اتصال فوق‌سریع و بدون قطعی به اینترنت آزاد\n🎁 با لینک دعوت اختصاصی من ${rewardGb} گیگابایت اینترنت هدیه بگیرید:\n` + refLink;
      const tgShareUrl = `https://t.me/share/url?url=${encodeURIComponent(refLink)}&text=${encodeURIComponent(shareMsg)}`;
      if (window.Telegram?.WebApp?.openTelegramLink) {
        try { window.Telegram.WebApp.openTelegramLink(tgShareUrl); } catch (e) { window.open(tgShareUrl, '_blank'); }
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

    const isUsage = currentStoryMode === 'usage';

    // Modern glassmorphism gradient card background
    const bgGrad = ctx.createLinearGradient(0, 0, 600, 780);
    bgGrad.addColorStop(0, '#0b0f19');
    bgGrad.addColorStop(0.5, isUsage ? '#0f172a' : '#131b2e');
    bgGrad.addColorStop(1, isUsage ? '#064e3b' : '#1e1b4b');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, 600, 780);

    // Subtle border
    ctx.strokeStyle = isUsage ? 'rgba(16, 185, 129, 0.45)' : 'rgba(99, 102, 241, 0.4)';
    ctx.lineWidth = 4;
    ctx.strokeRect(12, 12, 576, 756);

    // Decorative glow circles
    const drawGlow = (gx, gy, r, col) => {
      const g = ctx.createRadialGradient(gx, gy, 0, gx, gy, r);
      g.addColorStop(0, col);
      g.addColorStop(1, 'transparent');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(gx, gy, r, 0, Math.PI * 2);
      ctx.fill();
    };
    drawGlow(520, 80, 140, isUsage ? 'rgba(16, 185, 129, 0.22)' : 'rgba(6, 182, 212, 0.18)');
    drawGlow(80, 700, 160, isUsage ? 'rgba(6, 182, 212, 0.22)' : 'rgba(99, 102, 241, 0.22)');

    // Header bar
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 26px Vazirmatn, sans-serif';
    ctx.fillText(isUsage ? '📊 Remna Wrapped' : '⚡️ RemnaStore Pro', 300, 65);

    ctx.font = 'bold 12px Vazirmatn, sans-serif';
    ctx.fillStyle = isUsage ? '#34d399' : '#fbbf24';
    ctx.fillText(isUsage ? 'کارنامه مصرف اینترنت آزاد' : 'VIP PASS', 300, 92);

    // Avatar drawing
    const avatarImg = document.getElementById('storyCardAvatarImg');
    const avatarInitial = (document.getElementById('storyCardAvatarInitial')?.innerText || 'U').trim();
    const hasPhoto = avatarImg && !avatarImg.classList.contains('hidden') && avatarImg.complete && avatarImg.naturalWidth > 0;

    const avX = 300;
    const avY = 165;
    const avR = 48;

    if (hasPhoto) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(avX, avY, avR, 0, Math.PI * 2);
      ctx.clip();
      try {
        ctx.drawImage(avatarImg, avX - avR, avY - avR, avR * 2, avR * 2);
      } catch (e) {
        // Fallback to circle on tainted canvas
        ctx.fillStyle = '#3b82f6';
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 36px Vazirmatn, sans-serif';
        ctx.fillText(avatarInitial, avX, avY + 12);
      }
      ctx.restore();
    } else {
      const avGrad = ctx.createLinearGradient(avX - avR, avY - avR, avX + avR, avY + avR);
      avGrad.addColorStop(0, '#06b6d4');
      avGrad.addColorStop(1, '#6366f1');
      ctx.fillStyle = avGrad;
      ctx.beginPath();
      ctx.arc(avX, avY, avR, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 38px Vazirmatn, sans-serif';
      ctx.fillText(avatarInitial, avX, avY + 13);
    }

    // Avatar ring
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(avX, avY, avR + 2, 0, Math.PI * 2);
    ctx.stroke();

    // User Name and LTR Username
    const sName = (document.getElementById('storyCardName')?.innerText || 'کاربر گرامی').trim();
    const sUser = (document.getElementById('storyCardUsername')?.innerText || '').trim();

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 24px Vazirmatn, sans-serif';
    ctx.fillText(sName, 300, 250);

    ctx.fillStyle = '#60a5fa';
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText(sUser, 300, 276);

    // Metrics container box
    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.fillRect(50, 310, 500, 160);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(50, 310, 500, 160);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText(isUsage ? 'ترافیک مصرفی دوره:' : 'ترافیک باقی‌مانده اشتراک:', 300, 345);

    const sub = window.lastUserData?.active_sub;
    const sTraf = isUsage
      ? (sub?.traffic_used_gb != null
          ? fmtTraffic(sub.traffic_used_gb, { html: false })
          : ((document.getElementById('storyCardTraffic')?.innerText || '-- GB').trim()))
      : (sub?.traffic_remaining_gb != null
          ? fmtTraffic(sub.traffic_remaining_gb, { html: false })
          : ((document.getElementById('storyCardTraffic')?.innerText || '-- GB').trim()));
    ctx.fillStyle = '#34d399';
    ctx.font = 'bold 42px Vazirmatn, sans-serif';
    ctx.fillText(sTraf, 300, 400);

    const sDays = sub?.days_left != null
      ? `${toEnglishDigits(sub.days_left)} روز`
      : ((document.getElementById('storyCardDays')?.innerText || '--').trim());
    ctx.fillStyle = '#cbd5e1';
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText(`${sDays}  •  🟢 پایداری 100%`, 300, 442);

    // Bottom box (Referral promo OR Usage Wrapped showcase)
    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.fillRect(50, 490, 500, 240);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.strokeRect(50, 490, 500, 240);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 22px Vazirmatn, sans-serif';
    ctx.fillText(isUsage ? 'اتصال امن، سریع و پایدار' : 'اینترنت بدون قطعی و فوق‌سریع', 300, 535);

    if (isUsage) {
      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 17px Vazirmatn, sans-serif';
      ctx.fillText('🏆 کاربر برگزیده شبکه اینترنت آزاد رمنا', 300, 568);
      ctx.fillStyle = '#94a3b8';
      ctx.font = '14px Vazirmatn, sans-serif';
      ctx.fillText('🇩🇪 آلمان • 🇫🇮 فنلاند • 🇳🇱 هلند', 300, 620);
      ctx.fillStyle = '#64748b';
      ctx.font = '13px Vazirmatn, sans-serif';
      ctx.fillText('@RemnaBot  •  Verified High Speed Tunnel', 300, 680);
    } else {
      const rewardVal = window.lastUserData?.user?.referral_reward_gb
        ?? (document.getElementById('storyCardRewardGb')?.innerText || '5');
      const rewardGb = String(rewardVal).trim();
      ctx.fillStyle = '#34d399';
      ctx.font = 'bold 17px Vazirmatn, sans-serif';
      ctx.fillText(`🎁 با این کارت ${toEnglishDigits(rewardGb)} گیگابایت هدیه رایگان بگیرید`, 300, 568);
    }

    const qrImg = document.getElementById('storyCardQr');
    const finishDownload = () => {
      try {
        const link = document.createElement('a');
        link.download = 'remna-story-card.png';
        link.href = canvas.toDataURL('image/png');
        link.click();
        showToast('📸 پوستر استوری با بالاترین کیفیت در گالری ذخیره شد.');
      } catch (err) {
        showToast('⚠️ امکان ذخیره مستقیم پوستر به دلیل سیاست مرورگر نبود.');
      }
    };

    if (qrImg && qrImg.complete && qrImg.naturalWidth > 0) {
      try {
        ctx.drawImage(qrImg, 240, 595, 120, 120);
      } catch (e) {}
      finishDownload();
    } else {
      finishDownload();
    }
  });
}

window.setupStoryCard = setupStoryCard;

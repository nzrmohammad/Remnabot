/**
 * RemnaStore Pro - Story Cards & Viral Sharing Generator
 */

function _storyIsEn() {
  return typeof window !== 'undefined' && (Boolean(window.isAppEn?.()) || window.getAppLanguage?.() === 'en');
}
function _storyTr(fa, en) {
  return (typeof window !== 'undefined' && typeof window.trText === 'function')
    ? window.trText(fa, en)
    : (_storyIsEn() ? en : fa);
}

function setupStoryCard() {
  const closeStoryCardBtn = document.getElementById('closeStoryCardBtn');
  const downloadStoryBtn = document.getElementById('downloadStoryBtn');
  const shareTelegramStoryBtn = document.getElementById('shareTelegramStoryBtn');

  const storyModal = bindModal('storyCardModal', 'closeStoryCardBtn');
  window.openStoryCard = () => {
    (window.api?.haptic || window.hapticFeedback || hapticFeedback)('selection');
    const brandTitle = document.getElementById('storyBrandTitle');
    const brandBadge = document.getElementById('storyBrandBadge');
    const gamificationBanner = document.getElementById('storyGamificationBanner');
    const rewardText = document.getElementById('storyCardRewardText');
    const isEn = _storyIsEn();

    if (brandTitle) brandTitle.innerText = 'RemnaStore Pro';
    if (brandBadge) brandBadge.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span> VIP PASS';
    if (gamificationBanner) {
      gamificationBanner.innerHTML = isEn
        ? `<span class="font-black block text-amber-700 dark:text-amber-300 mb-0.5"><img src="/static/img/icons/award.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle mr-1" width="16" height="16" alt="" />Story & Share Reward:</span>Share this card on your Telegram Story; once your invited friends join and complete their first purchase, you'll receive a <b id="storyRewardBannerGb" class="text-amber-700 dark:text-amber-300 font-sans">5</b> GB referral bonus!`
        : '<span class="font-black block text-amber-700 dark:text-amber-300 mb-0.5"><img src="/static/img/icons/award.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle ml-1" width="16" height="16" alt="" />پاداش استوری و اشتراک‌گذاری:</span>با انتشار این تصویر در استوری تلگرام، دوستانتان عضو شده و پس از اولین خریدشان، <b id="storyRewardBannerGb" class="text-amber-700 dark:text-amber-300 font-sans">5</b> گیگابایت پاداش معرف برای شما واریز می‌شود!';
    }
    if (rewardText) {
      const rewardVal = window.lastUserData?.user?.referral_reward_gb ?? (document.getElementById('storyCardRewardGb')?.innerText || '5');
      const rStr = toEnglishDigits(rewardVal);
      rewardText.innerHTML = isEn
        ? `<img src="/static/img/icons/gift.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle mr-1" width="16" height="16" alt="" />Get <span id="storyCardRewardGb" class="font-sans">${rStr}</span> GB free gift with this card`
        : `<img src="/static/img/icons/gift.svg?v=fl2" class="ui-icon-img w-4 h-4 shrink-0 inline-block align-middle ml-1" width="16" height="16" alt="" />با این کارت <span id="storyCardRewardGb" class="font-sans">${rStr}</span> گیگابایت هدیه بگیرید`;
    }
    if (typeof window.renderEngagementFeatures === 'function' && window.lastUserData) {
      window.renderEngagementFeatures(window.lastUserData);
    }
    storyModal.open();
  };

  shareTelegramStoryBtn?.addEventListener('click', () => {
    (window.api?.haptic || window.hapticFeedback || hapticFeedback)('light');
    const botUser = window.lastUserData?.bot_username || window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || '';
    const fallbackRef = window.buildRefLink(botUser, window.lastUserData?.user?.id);
    const refLink = window.currentReferralLink || fallbackRef;
    copyToClipboard(refLink);

    const rewardVal = window.lastUserData?.user?.referral_reward_gb
      ?? (document.getElementById('storyCardRewardGb')?.innerText || '5');
    const rewardTraffic = fmtTraffic(Number(rewardVal) || 5, { html: false, precision: 0 });
    const rewardGb = String(rewardVal).trim();
    const isEn = _storyIsEn();
    let sharedViaStory = false;
    const qrEl = document.getElementById('storyCardQr');
    const mediaUrl = qrEl?.src || '';
    if (window.Telegram?.WebApp?.shareToStory && mediaUrl) {
      try {
        const storyCaption = isEn
          ? `🚀 High-speed, uninterrupted internet access\n🎁 Claim ${rewardTraffic} free gift data with this card!`
          : `🚀 اتصال پرسرعت به اینترنت بدون قطعی\n🎁 با این کارت ${rewardGb} گیگابایت هدیه رایگان بگیرید!`;
        window.Telegram.WebApp.shareToStory(mediaUrl, {
          text: storyCaption,
          widget_link: {
            url: refLink,
            name: _storyTr('دریافت اینترنت هدیه', 'Claim Free Data'),
          },
        });
        sharedViaStory = true;
      } catch (e) {
        sharedViaStory = false;
      }
    }

    if (!sharedViaStory) {
      const shareMsg = (isEn
        ? `🚀 Ultra-fast, uninterrupted internet access\n🎁 Join via my invite link to claim ${rewardTraffic} free gift traffic:\n`
        : `🚀 اتصال فوق‌سریع و بدون قطعی به اینترنت آزاد\n🎁 با لینک دعوت اختصاصی من ${rewardGb} گیگابایت اینترنت هدیه بگیرید:\n`) + refLink;
      const tgShareUrl = `https://t.me/share/url?url=${encodeURIComponent(refLink)}&text=${encodeURIComponent(shareMsg)}`;
      if (window.Telegram?.WebApp?.openTelegramLink) {
        try { window.Telegram.WebApp.openTelegramLink(tgShareUrl); } catch (e) { window.openExternalUrl ? window.openExternalUrl(tgShareUrl) : window.open(tgShareUrl, '_blank', 'noopener,noreferrer'); }
      } else {
        window.openExternalUrl ? window.openExternalUrl(tgShareUrl) : window.open(tgShareUrl, '_blank', 'noopener,noreferrer');
      }
    }
    showToast(_storyTr('🚀 لینک دعوت کپی شد و صفحه اشتراک‌گذاری در استوری باز گردید.', '🚀 Invite link copied and story sharing opened.'));
  });

  downloadStoryBtn?.addEventListener('click', () => {
    const canvas = document.createElement('canvas');
    canvas.width = 600;
    canvas.height = 780;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      showToast(_storyTr('⚠️ مرورگر شما از ایجاد تصویر پشتیبانی نمی‌کند.', '⚠️ Your browser does not support image generation.'));
      return;
    }

    const activeTheme = typeof window.getActiveStoryCanvasTheme === 'function' ? window.getActiveStoryCanvasTheme() : null;
    const bgFrom = activeTheme?.bg_from || '#0b0f19';
    const bgMid = activeTheme?.bg_mid || '#131b2e';
    const bgTo = activeTheme?.bg_to || '#1e1b4b';
    const borderCol = activeTheme?.border_rgba || 'rgba(99, 102, 241, 0.4)';
    const accentCol = activeTheme?.accent || '#38bdf8';
    const secCol = activeTheme?.secondary || '#6366f1';

    // Modern glassmorphism gradient card background
    const bgGrad = ctx.createLinearGradient(0, 0, 600, 780);
    bgGrad.addColorStop(0, bgFrom);
    bgGrad.addColorStop(0.5, bgMid);
    bgGrad.addColorStop(1, bgTo);
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, 600, 780);

    // Subtle border
    ctx.strokeStyle = borderCol;
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
    ctx.save();
    ctx.globalAlpha = 0.22;
    drawGlow(520, 80, 140, accentCol);
    drawGlow(80, 700, 160, secCol);
    ctx.restore();

    // Header bar
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 26px Vazirmatn, sans-serif';
    ctx.fillText('⚡️ RemnaStore Pro', 300, 65);

    ctx.font = 'bold 12px Vazirmatn, sans-serif';
    ctx.fillStyle = '#fbbf24';
    ctx.fillText('VIP PASS', 300, 92);

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
    const isEn = _storyIsEn();
    const sName = (document.getElementById('storyCardName')?.innerText || _storyTr('کاربر گرامی', 'Valued User')).trim();
    const sUser = (document.getElementById('storyCardUsername')?.innerText || '').trim();

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 24px Vazirmatn, sans-serif';
    ctx.fillText(sName, 300, 250);

    ctx.fillStyle = accentCol;
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText(sUser, 300, 276);

    const champBadge = typeof window.getActiveChampionBadge === 'function' ? window.getActiveChampionBadge() : null;
    if (champBadge?.title) {
      ctx.fillStyle = '#fbbf24';
      ctx.font = 'bold 14px Vazirmatn, sans-serif';
      ctx.fillText(champBadge.title, 300, 299);
    }

    // Metrics container box
    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.fillRect(50, 310, 500, 160);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(50, 310, 500, 160);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText(_storyTr('ترافیک باقی‌مانده اشتراک:', 'Remaining Subscription Traffic:'), 300, 345);

    const sub = window.lastUserData?.active_sub;
    const sTraf = sub?.traffic_remaining_gb != null
      ? fmtTraffic(sub.traffic_remaining_gb, { html: false })
      : ((document.getElementById('storyCardTraffic')?.innerText || '-- GB').trim());
    ctx.fillStyle = '#34d399';
    ctx.font = 'bold 42px Vazirmatn, sans-serif';
    ctx.fillText(sTraf, 300, 400);

    const sDays = sub?.days_left != null
      ? (isEn ? `${toEnglishDigits(sub.days_left)} days` : `${toEnglishDigits(sub.days_left)} روز`)
      : ((document.getElementById('storyCardDays')?.innerText || '--').trim());
    ctx.fillStyle = '#cbd5e1';
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText(isEn ? `${sDays}  •  🟢 100% Uptime` : `${sDays}  •  🟢 پایداری 100%`, 300, 442);

    // Bottom box (Referral promo showcase)
    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.fillRect(50, 490, 500, 240);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.strokeRect(50, 490, 500, 240);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 22px Vazirmatn, sans-serif';
    ctx.fillText(_storyTr('اینترنت بدون قطعی و فوق‌سریع', 'Ultra-Fast Uninterrupted Internet'), 300, 535);

    const rewardVal = window.lastUserData?.user?.referral_reward_gb
      ?? (document.getElementById('storyCardRewardGb')?.innerText || '5');
    const rewardGb = String(rewardVal).trim();
    const rewardTraffic = fmtTraffic(Number(rewardVal) || 5, { html: false, precision: 0 });
    ctx.fillStyle = '#34d399';
    ctx.font = 'bold 17px Vazirmatn, sans-serif';
    ctx.fillText(
      isEn ? `🎁 Claim ${rewardTraffic} free gift data with this card` : `🎁 با این کارت ${toEnglishDigits(rewardGb)} گیگابایت هدیه رایگان بگیرید`,
      300,
      568
    );

    const qrImg = document.getElementById('storyCardQr');
    const finishDownload = () => {
      try {
        const link = document.createElement('a');
        link.download = 'remna-story-card.png';
        link.href = canvas.toDataURL('image/png');
        link.click();
        showToast(_storyTr('📸 پوستر استوری با بالاترین کیفیت در گالری ذخیره شد.', '📸 Story poster saved in HD.'));
      } catch (err) {
        showToast(_storyTr('⚠️ امکان ذخیره مستقیم پوستر به دلیل سیاست مرورگر نبود.', '⚠️ Direct image download was blocked by your browser.'));
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

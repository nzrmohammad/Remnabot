/**
 * RemnaStore Pro - Story Cards & Viral Sharing Generator
 */

function setupStoryCard() {
  const openStoryCardBtn = document.getElementById('openStoryCardBtn');
  const closeStoryCardBtn = document.getElementById('closeStoryCardBtn');
  const downloadStoryBtn = document.getElementById('downloadStoryBtn');
  const shareTelegramStoryBtn = document.getElementById('shareTelegramStoryBtn');

  openStoryCardBtn?.addEventListener('click', () => openModal('storyCardModal'));
  closeStoryCardBtn?.addEventListener('click', () => closeModal('storyCardModal'));

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
            name: 'دریافت اینترنت هدیه',
          },
        });
        sharedViaStory = true;
      } catch (e) {
        sharedViaStory = false;
      }
    }

    if (!sharedViaStory) {
      const shareMsg = '🚀 اتصال فوق‌سریع و بدون قطعی به اینترنت آزاد\n🎁 با لینک دعوت اختصاصی من ۱ گیگابایت اینترنت هدیه بگیرید:\n' + refLink;
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

    // Modern glassmorphism gradient card background
    const bgGrad = ctx.createLinearGradient(0, 0, 600, 780);
    bgGrad.addColorStop(0, '#0b0f19');
    bgGrad.addColorStop(0.5, '#131b2e');
    bgGrad.addColorStop(1, '#1e1b4b');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, 600, 780);

    // Subtle border
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.4)';
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
    drawGlow(520, 80, 140, 'rgba(6, 182, 212, 0.18)');
    drawGlow(80, 700, 160, 'rgba(99, 102, 241, 0.22)');

    // Header bar
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 26px Vazirmatn, sans-serif';
    ctx.fillText('⚡️ RemnaStore Pro', 300, 65);

    ctx.font = 'bold 12px monospace';
    ctx.fillStyle = '#fbbf24';
    ctx.fillText('VIP MEMBER', 300, 92);

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
    ctx.font = '15px monospace';
    ctx.fillText(sUser, 300, 276);

    // Metrics container box
    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.fillRect(50, 310, 500, 160);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1.5;
    ctx.strokeRect(50, 310, 500, 160);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText('ترافیک باقی‌مانده اشتراک:', 300, 345);

    const sTraf = (document.getElementById('storyCardTraffic')?.innerText || '-- GB').trim();
    ctx.fillStyle = '#34d399';
    ctx.font = 'bold 42px monospace';
    ctx.fillText(sTraf, 300, 400);

    const sDays = (document.getElementById('storyCardDays')?.innerText || '--').trim();
    ctx.fillStyle = '#cbd5e1';
    ctx.font = '15px Vazirmatn, sans-serif';
    ctx.fillText(`${sDays}  •  🟢 پایداری 100%`, 300, 442);

    // Bottom Viral Referral Promo box
    ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
    ctx.fillRect(50, 490, 500, 240);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.strokeRect(50, 490, 500, 240);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 22px Vazirmatn, sans-serif';
    ctx.fillText('اینترنت بدون قطعی و فوق‌سریع', 300, 535);

    ctx.fillStyle = '#34d399';
    ctx.font = 'bold 17px Vazirmatn, sans-serif';
    ctx.fillText('🎁 با این کارت ۱ گیگابایت هدیه رایگان بگیرید', 300, 568);

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

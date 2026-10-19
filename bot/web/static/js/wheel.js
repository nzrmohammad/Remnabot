/**
 * RemnaStore Pro - Lucky Wheel & 24h Cooldown
 */

let hasSpunFreeWheel = false;
let currentWheelRotation = 0;
let isSpinningWheel = false;
let wheelCooldownSeconds = 0;
let wheelCountdownInterval = null;

const prizeMap = {
  '1gb': 0,
  'blank_1': 1,
  'discount10': 2,
  '500mb': 3,
  '2gb': 4,
  'blank_2': 4,
  'blank': 1,
  'again': 5
};

const localPrizes = [
  { id: '1gb', name: '1 GB ترافیک هدیه', icon: '🎁', isAgain: false, isZero: false },
  { id: 'blank_1', name: 'پوچ (شانس بعدی فردا)', icon: '❌', isAgain: false, isZero: true },
  { id: 'discount10', name: '۱۰٪ کد تخفیف ویژه (کد: OFF10)', icon: '🎟', isAgain: false, isZero: false },
  { id: '500mb', name: '500 MB ترافیک هدیه', icon: '⚡️', isAgain: false, isZero: false },
  { id: '2gb', name: '2 GB ترافیک هدیه (سوپر شانس)', icon: '👑', isAgain: false, isZero: false },
  { id: 'again', name: 'دوباره (شانس مجدد!)', icon: '🔄', isAgain: true, isZero: false }
];

function showWheelResultModal({ icon = '🎉', title = 'تبریک!', message = '', couponCode = null, isError = false }) {
  const modal = document.getElementById('wheelResultModal');
  const iconEl = document.getElementById('wheelResultModalIcon');
  const iconBox = document.getElementById('wheelResultModalIconBox');
  const titleEl = document.getElementById('wheelResultModalTitle');
  const bodyEl = document.getElementById('wheelResultModalBody');
  const couponBox = document.getElementById('wheelResultModalCouponBox');
  const couponCodeEl = document.getElementById('wheelResultModalCouponCode');

  if (!modal) {
    if (window.showToast) window.showToast(message);
    return;
  }

  if (iconEl) iconEl.innerText = icon;
  if (titleEl) titleEl.innerText = title;
  if (bodyEl) bodyEl.innerHTML = message;

  if (iconBox) {
    if (isError) {
      iconBox.className = 'w-16 h-16 rounded-2xl mx-auto flex items-center justify-center text-3xl shadow-lg border border-rose-500/30 bg-rose-500/10 mt-1';
    } else if (couponCode) {
      iconBox.className = 'w-16 h-16 rounded-2xl mx-auto flex items-center justify-center text-3xl shadow-lg border border-amber-500/40 bg-amber-500/15 mt-1';
    } else {
      iconBox.className = 'w-16 h-16 rounded-2xl mx-auto flex items-center justify-center text-3xl shadow-lg border border-emerald-500/30 bg-emerald-500/10 mt-1';
    }
  }

  if (couponBox && couponCodeEl) {
    if (couponCode) {
      couponCodeEl.innerText = couponCode;
      couponBox.classList.remove('hidden');
      const copyBtn = document.getElementById('copyWheelCouponBtn');
      if (copyBtn) {
        copyBtn.onclick = () => {
          if (typeof copyToClipboard === 'function') {
            copyToClipboard(couponCode, 'کد تخفیف کپی شد');
          } else if (window.copyToClipboard) {
            window.copyToClipboard(couponCode, 'کد تخفیف کپی شد');
          }
        };
      }
    } else {
      couponBox.classList.add('hidden');
    }
  }

  modal.classList.remove('hidden');
  const hapticFn = window.api?.haptic || window.hapticFeedback || (typeof hapticFeedback === 'function' ? hapticFeedback : null);
  if (hapticFn) hapticFn(isError ? 'error' : 'success');
}

function closeWheelResultModal() {
  const modal = document.getElementById('wheelResultModal');
  if (modal) modal.classList.add('hidden');
}
window.closeWheelResultModal = closeWheelResultModal;
window.showWheelResultModal = showWheelResultModal;

let currentWheelStreak = 0;
let currentWheelMultiplier = 1.0;
let currentWheelTickets = 0;
let wheelTargetEndTime = 0;

function checkAndUpdateWheelCooldown() {
  if (wheelTargetEndTime > 0) {
    const remaining = Math.max(0, Math.round((wheelTargetEndTime - Date.now()) / 1000));
    wheelCooldownSeconds = remaining;
    if (remaining <= 0) {
      wheelTargetEndTime = 0;
      wheelCooldownSeconds = 0;
      if (wheelCountdownInterval) clearInterval(wheelCountdownInterval);
      const timerBox = document.getElementById('wheelTimerContainer');
      if (timerBox) timerBox.classList.add('hidden');
      if (window.lastUserData?.wheel_status) {
        window.lastUserData.wheel_status.next_spin_seconds = 0;
        window.lastUserData.wheel_status.can_spin = true;
      }
      updateWheelUIState(true, true, 0, currentWheelStreak, currentWheelMultiplier, currentWheelTickets);
      return 0;
    }
    return remaining;
  }
  return wheelCooldownSeconds;
}

function startWheelCountdown(sec) {
  const s = Math.max(0, Math.round(sec));
  wheelCooldownSeconds = s;
  wheelTargetEndTime = s > 0 ? (Date.now() + s * 1000) : 0;
  const timerBox = document.getElementById('wheelTimerContainer');
  const timerText = document.getElementById('wheelCountdownText');

  if (s <= 0) {
    if (wheelCountdownInterval) clearInterval(wheelCountdownInterval);
    if (timerBox) timerBox.classList.add('hidden');
    return;
  }

  if (timerBox) timerBox.classList.remove('hidden');
  if (timerText) timerText.innerText = formatCountdown(wheelCooldownSeconds);

  if (wheelCountdownInterval) clearInterval(wheelCountdownInterval);
  wheelCountdownInterval = setInterval(() => {
    const rem = checkAndUpdateWheelCooldown();
    if (rem > 0 && timerText) {
      timerText.innerText = formatCountdown(rem);
    }
  }, 1000);
}

function updateWheelUIState(canSpin, hasActiveSub, nextSeconds, streak, multiplier, tickets) {
  if (streak !== undefined && streak !== null) currentWheelStreak = Number(streak) || 0;
  if (multiplier !== undefined && multiplier !== null) currentWheelMultiplier = Number(multiplier) || 1.0;
  if (tickets !== undefined && tickets !== null) currentWheelTickets = Number(tickets) || 0;

  const spinBtn = document.getElementById('spinWheelBtn');
  const timerBox = document.getElementById('wheelTimerContainer');
  const warningBox = document.getElementById('wheelSubWarning');
  const wheelSubEl = document.querySelector('.lucky-wheel-sub');
  const streakTextEl = document.getElementById('wheelStreakText');
  const streakBadgeEl = document.getElementById('wheelStreakBadge');
  const ticketsTextEl = document.getElementById('wheelTicketsText');
  const ticketsBadgeEl = document.getElementById('wheelTicketsBadge');

  const fNum = (n) => (typeof toPersianDigits === 'function' ? toPersianDigits(n) : n);

  if (streakTextEl) {
    const multStr = currentWheelMultiplier > 1.0 ? ` (×${fNum(currentWheelMultiplier.toFixed(1))})` : '';
    streakTextEl.textContent = `استریک: ${fNum(currentWheelStreak)} روز${multStr}`;
  }
  if (streakBadgeEl) {
    streakBadgeEl.className = currentWheelStreak >= 3 ? 'badge-streak streak-boost' : 'badge-streak';
  }

  if (ticketsTextEl) {
    ticketsTextEl.textContent = `${fNum(currentWheelTickets)} تیکت`;
  }
  if (ticketsBadgeEl) {
    ticketsBadgeEl.className = currentWheelTickets > 0 ? 'badge-ticket has-tickets' : 'badge-ticket';
  }

  const hasTicket = currentWheelTickets > 0;
  const isCooldown = nextSeconds > 0;

  if (wheelSubEl) {
    if (!hasActiveSub) {
      wheelSubEl.textContent = '🔒 قفل (ویژه اشتراک‌های فعال)';
      wheelSubEl.classList.remove('text-slate-300', 'text-emerald-400', 'text-purple-400');
      wheelSubEl.classList.add('text-amber-400/80');
    } else if (isCooldown && hasTicket) {
      wheelSubEl.textContent = `🎫 شانس با تیکت دعوت (${fNum(currentWheelTickets)} عدد)`;
      wheelSubEl.classList.remove('text-amber-400/80', 'text-slate-300', 'text-emerald-400');
      wheelSubEl.classList.add('text-purple-400');
    } else if (isCooldown) {
      wheelSubEl.textContent = '⏳ شانس بعدی تا ۲۴ ساعت';
      wheelSubEl.classList.remove('text-amber-400/80', 'text-emerald-400', 'text-purple-400');
      wheelSubEl.classList.add('text-slate-300');
    } else {
      wheelSubEl.textContent = '🎁 ۱ شانس روزانه فعال';
      wheelSubEl.classList.remove('text-amber-400/80', 'text-slate-300', 'text-purple-400');
      wheelSubEl.classList.add('text-emerald-400');
    }
  }

  if (!spinBtn) return;

  if (!hasActiveSub) {
    spinBtn.disabled = true;
    spinBtn.innerHTML = '<span class="text-[10px] font-bold">🔒 نیاز به اشتراک</span>';
    if (warningBox) warningBox.classList.remove('hidden');
    if (timerBox) timerBox.classList.add('hidden');
    return;
  }
  if (warningBox) warningBox.classList.add('hidden');

  if (isCooldown) {
    startWheelCountdown(nextSeconds);
    if (hasTicket) {
      spinBtn.disabled = false;
      spinBtn.innerHTML = '<span class="text-[10px] font-extrabold tracking-tight leading-tight">بچرخون!<br/><span class="text-[8px] opacity-90">(۱🎫)</span></span>';
    } else {
      spinBtn.disabled = true;
      spinBtn.innerHTML = '<span class="text-[10px] font-bold">🔒 ۲۴ ساعت</span>';
    }
  } else {
    if (wheelCountdownInterval) clearInterval(wheelCountdownInterval);
    if (timerBox) timerBox.classList.add('hidden');
    spinBtn.disabled = false;
    spinBtn.innerHTML = '<span class="text-[10px] font-extrabold tracking-tight">بچرخون!</span>';
  }
}

function setupLuckyWheel() {
  const luckyWheelModal = document.getElementById('luckyWheelModal');
  const openLuckyWheelBtn = document.getElementById('openLuckyWheelBtn');
  const closeLuckyWheelBtn = document.getElementById('closeLuckyWheelBtn');
  const spinWheelBtn = document.getElementById('spinWheelBtn');
  const wheelContainer = document.getElementById('wheelContainer');
  const wheelResultText = document.getElementById('wheelResultText');

  const wheelModal = bindModal('luckyWheelModal', 'closeLuckyWheelBtn');
  openLuckyWheelBtn?.addEventListener('click', () => {
    window.api?.haptic?.('selection');
    checkAndUpdateWheelCooldown();
    if (window.lastUserData?.wheel_status) {
      const ws = window.lastUserData.wheel_status;
      const effectiveCooldown = wheelCooldownSeconds;
      updateWheelUIState(
        effectiveCooldown <= 0 || (currentWheelTickets > 0),
        ws.has_active_sub,
        effectiveCooldown,
        ws.streak || 0,
        ws.streak_multiplier || 1.0,
        ws.spin_tickets || 0
      );
    }
    wheelModal.open();
  });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) checkAndUpdateWheelCooldown();
  });
  window.addEventListener('focus', () => {
    checkAndUpdateWheelCooldown();
  });

  spinWheelBtn?.addEventListener('click', async () => {
    if (isSpinningWheel) return;
    const ws = window.lastUserData?.wheel_status;
    if (ws && !ws.has_active_sub) {
      showWheelResultModal({
        icon: '🔒',
        title: 'نیاز به اشتراک فعال',
        message: 'برای استفاده از گردونه شانس، داشتن حداقل یک اشتراک فعال در پنل الزامی است.',
        isError: true,
      });
      return;
    }

    const remainingSec = checkAndUpdateWheelCooldown();
    const isCooldownNow = remainingSec > 0;
    const hasTickets = currentWheelTickets > 0;
    if (isCooldownNow && !hasTickets) {
      showWheelResultModal({
        icon: '⏳',
        title: 'مهلت ۲۴ ساعته',
        message: `گردونه شانس هر ۲۴ ساعت یک‌بار فعال می‌شود.<br/><span class="text-amber-400 font-mono font-bold text-sm block mt-2" dir="ltr">${formatCountdown(remainingSec)}</span><span class="text-[11px] text-slate-400 block mt-0.5">زمان باقیمانده تا شانس رایگان روزانه شما (با معرفی دوستان تیکت شانس بدون محدودیت دریافت کنید!)</span>`,
        isError: true,
      });
      return;
    }

    const useTicket = isCooldownNow && hasTickets;

    isSpinningWheel = true;
    spinBtnState(spinWheelBtn, true, '...');

    let chosenPrize = null;
    let targetIndex = 0;
    let spinResult = null;

    try {
      const res = await window.api.spinWheel(useTicket ? { use_ticket: true } : {});
      spinResult = res;
      if (res && res.ok && res.prize) {
        chosenPrize = res.prize;
        targetIndex = prizeMap[chosenPrize.id] ?? 0;
        if (res.streak !== undefined) currentWheelStreak = res.streak;
        if (res.streak_multiplier !== undefined) currentWheelMultiplier = res.streak_multiplier;
        if (res.spin_tickets !== undefined) currentWheelTickets = res.spin_tickets;
        if (window.lastUserData?.wheel_status) {
          window.lastUserData.wheel_status.streak = currentWheelStreak;
          window.lastUserData.wheel_status.streak_multiplier = currentWheelMultiplier;
          window.lastUserData.wheel_status.spin_tickets = currentWheelTickets;
        }
      } else if (res && !res.ok && res.error) {
        if (res.code === 'channel_required' && res.channel_url) {
          showWheelResultModal({
            icon: '📢',
            title: 'عضویت در کانال الزامی است',
            message: `${res.error}<div class="mt-3"><a href="${res.channel_url}" target="_blank" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow transition active:scale-95"><span>📢</span><span>عضویت در کانال رسمی</span></a></div>`,
            isError: true,
          });
        } else {
          showWheelResultModal({
            icon: '⚠️',
            title: 'خطا در گردونه',
            message: res.error,
            isError: true,
          });
        }
        isSpinningWheel = false;
        if (res.next_spin_seconds) {
          updateWheelUIState(currentWheelTickets > 0, true, res.next_spin_seconds, currentWheelStreak, currentWheelMultiplier, currentWheelTickets);
        } else {
          spinBtnState(spinWheelBtn, false, 'بچرخون!');
        }
        return;
      }
    } catch (err) {
      console.debug('Wheel spin API error', err);
    }

    if (!chosenPrize) {
      isSpinningWheel = false;
      spinBtnState(spinWheelBtn, false, 'بچرخون!');
      showWheelResultModal({
        icon: '⚠️',
        title: 'خطا در برقراری ارتباط',
        message: 'امکان دریافت پاسخ از سرور وجود ندارد. لطفاً اتصال اینترنت خود را بررسی نمایید.',
        isError: true,
      });
      return;
    }

    const targetDegree = (360 - (targetIndex * 60)) % 360;
    const prevMod = currentWheelRotation % 360;
    const diff = (targetDegree - prevMod + 360) % 360;
    const fullTurns = 5 * 360;
    currentWheelRotation += fullTurns + diff;

    if (wheelContainer) {
      wheelContainer.style.transform = `rotate(${currentWheelRotation}deg)`;
    }

    setTimeout(() => {
      isSpinningWheel = false;
      const hapticFn = window.api?.haptic || window.hapticFeedback || (typeof hapticFeedback === 'function' ? hapticFeedback : null);
      if (hapticFn) hapticFn('success');

      const isAgain = chosenPrize.id === 'again';
      const isBlank = chosenPrize.id === 'blank' || chosenPrize.id === 'blank_1' || chosenPrize.id === 'blank_2' || chosenPrize.type === 'blank';
      const usedTicket = spinResult?.used_ticket;
      const fNum = (n) => typeof toPersianDigits === 'function' ? toPersianDigits(n) : n;

      let streakNote = '';
      if (currentWheelStreak > 1) {
        streakNote = `<div class="mt-2 text-[11px] text-amber-300/90 font-medium">🔥 استریک شما: <b>${fNum(currentWheelStreak)} روز</b> پی‌درپی (شانس جوایز ویژه فعال است)</div>`;
      }
      let ticketNote = '';
      if (usedTicket) {
        ticketNote = `<div class="mt-1 text-[10px] text-purple-300 font-medium">🎫 ۱ تیکت مصرف شد (باقیمانده: <b>${fNum(currentWheelTickets)}</b>)</div>`;
      }

      if (isAgain) {
        spinBtnState(spinWheelBtn, false, 'بچرخون!');
        if (wheelResultText) wheelResultText.innerHTML = '🔄 <b>شانس مجدد!</b> گردونه دوباره برای شما شارژ شد، همین الان بچرخون!';
        showWheelResultModal({
          icon: '🔄',
          title: 'شانس مجدد برنده شدید!',
          message: `گردونه مجدداً برای شما شارژ شد! همین حالا دکمه وسط را لمس کنید و یک‌بار دیگر شانس خود را امتحان فرمایید.${ticketNote}`,
        });
      } else {
        const nextSec = usedTicket ? wheelCooldownSeconds : 86400;
        updateWheelUIState(currentWheelTickets > 0, true, nextSec, currentWheelStreak, currentWheelMultiplier, currentWheelTickets);

        if (isBlank) {
          if (wheelResultText) wheelResultText.innerHTML = `❌ <b>متاسفانه پوچ شد!</b> ${usedTicket ? 'می‌توانید با تیکت مجدد شانس خود را امتحان کنید.' : 'شانس بعدی شما ۲۴ ساعت دیگر فعال می‌شود.'}`;
          showWheelResultModal({
            icon: '❌',
            title: 'متاسفانه این بار پوچ شد!',
            message: `در این چرخش جایزه‌ای به شما تعلق نگرفت.<br/><span class="text-slate-400 block mt-1">${usedTicket ? 'تیکت مصرف شد، اما مهلت روزانه شما محفوظ است.' : 'شانس بعدی شما دقیقاً <b>۲۴ ساعت دیگر</b> فعال خواهد شد. فردا حتماً دوباره سر بزنید!'}</span>${streakNote}${ticketNote}`,
            isError: true,
          });
        } else if (chosenPrize.code || chosenPrize.type === 'coupon') {
          const couponCode = chosenPrize.code || 'OFF10';
          if (chosenPrize.code) {
            try {
              const localCoupons = JSON.parse(localStorage.getItem('user_won_coupons') || '[]');
              localCoupons.unshift({
                code: chosenPrize.code,
                discount_percent: chosenPrize.percent || 10,
                expires_at: new Date(Date.now() + 7 * 86400000).toISOString(),
              });
              localStorage.setItem('user_won_coupons', JSON.stringify(localCoupons.slice(0, 10)));
            } catch(e) {}
          }
          if (wheelResultText) {
            wheelResultText.innerHTML = `🎉 <b>تبریک!</b> شما برنده <b class="text-amber-400 font-bold">${chosenPrize.name || chosenPrize.text}</b> شدید!<br/><span class="font-mono text-cyan-400 font-bold block mt-1 select-all" dir="ltr">کد: ${couponCode}</span><span class="text-[11px] text-slate-400 block mt-0.5">⏱ مهلت استفاده: ۷ روز در تب فروشگاه</span>`;
          }
          showWheelResultModal({
            icon: '🎟',
            title: 'تبریک! برنده کد تخفیف شدید',
            message: `کد تخفیف اختصاصی ۱۰٪ برای شما فعال شد. می‌توانید در خرید بعدی از تب فروشگاه آن را اعمال کنید.${streakNote}${ticketNote}`,
            couponCode: couponCode,
          });
        } else {
          const rawPrize = chosenPrize.id === '500mb' ? '500 MB' : (chosenPrize.value || 1);
          const parsed = typeof fmtTrafficValue === 'function' ? fmtTrafficValue(rawPrize) : { num: 1, unit: 'GB' };
          const valNum = typeof toEnglishDigits === 'function' ? toEnglishDigits(parsed.num) : parsed.num;
          const unit = parsed.unit;
          if (wheelResultText) wheelResultText.innerHTML = `🎉 <b>تبریک فوق‌العاده!</b> شما برنده <b class="text-emerald-400 font-bold" dir="ltr"><span class="font-mono">${valNum}</span> ${unit}</b> ترافیک رایگان شدید!`;
          showWheelResultModal({
            icon: '🎁',
            title: 'تبریک فوق‌العاده!',
            message: `شما برنده ترافیک رایگان شدید:<br/><div class="my-2 inline-flex items-baseline gap-1" dir="ltr"><b class="text-2xl font-black font-mono text-emerald-500 dark:text-emerald-400">${valNum}</b><span class="text-sm font-bold text-slate-600 dark:text-slate-300 font-sans">${unit}</span></div><br/><span class="text-slate-400 text-[11px]">این هدیه به صورت خودکار به اشتراک فعال شما اضافه شد.</span>${streakNote}${ticketNote}`,
          });
        }
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      }
    }, 3650);
  });
}

function spinBtnState(btn, disabled, text) {
  if (!btn) return;
  btn.disabled = disabled;
  btn.innerHTML = `<span class="text-[10px] font-extrabold tracking-tight">${text}</span>`;
}

window.updateWheelUIState = updateWheelUIState;
window.setupLuckyWheel = setupLuckyWheel;

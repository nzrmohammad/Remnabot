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
  '1day': 1,
  'discount10': 2,
  '500mb': 3,
  'blank': 4,
  'again': 5
};

const localPrizes = [
  { id: '1gb', name: '1 GB ترافیک هدیه', icon: '🎁', isAgain: false, isZero: false },
  { id: '1day', name: '1 روز اشتراک VIP رایگان', icon: '💎', isAgain: false, isZero: false },
  { id: 'discount10', name: '۱۰٪ کد تخفیف ویژه (کد: OFF10)', icon: '🎟', isAgain: false, isZero: false },
  { id: '500mb', name: '500 MB ترافیک هدیه', icon: '⚡️', isAgain: false, isZero: false },
  { id: 'blank', name: 'پوچ (شانس بعدی فردا)', icon: '❌', isAgain: false, isZero: true },
  { id: 'again', name: 'دوباره (شانس مجدد!)', icon: '🔄', isAgain: true, isZero: false }
];

function startWheelCountdown(sec) {
  wheelCooldownSeconds = sec;
  const timerBox = document.getElementById('wheelTimerContainer');
  const timerText = document.getElementById('wheelCountdownText');
  if (timerBox) timerBox.classList.remove('hidden');
  if (timerText) timerText.innerText = formatCountdown(wheelCooldownSeconds);

  if (wheelCountdownInterval) clearInterval(wheelCountdownInterval);
  wheelCountdownInterval = setInterval(() => {
    wheelCooldownSeconds -= 1;
    if (wheelCooldownSeconds <= 0) {
      clearInterval(wheelCountdownInterval);
      if (timerBox) timerBox.classList.add('hidden');
      updateWheelUIState(true, true, 0);
    } else {
      if (timerText) timerText.innerText = formatCountdown(wheelCooldownSeconds);
    }
  }, 1000);
}

function updateWheelUIState(canSpin, hasActiveSub, nextSeconds) {
  const spinBtn = document.getElementById('spinWheelBtn');
  const timerBox = document.getElementById('wheelTimerContainer');
  const warningBox = document.getElementById('wheelSubWarning');
  if (!spinBtn) return;

  if (!hasActiveSub) {
    spinBtn.disabled = true;
    spinBtn.innerHTML = '<span class="text-[9px] font-bold">🔒 نیاز به اشتراک</span>';
    if (warningBox) warningBox.classList.remove('hidden');
    if (timerBox) timerBox.classList.add('hidden');
    return;
  }
  if (warningBox) warningBox.classList.add('hidden');

  if (nextSeconds > 0) {
    spinBtn.disabled = true;
    spinBtn.innerHTML = '<span class="text-[9px] font-bold">🔒 ۲۴ ساعت</span>';
    startWheelCountdown(nextSeconds);
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

  openLuckyWheelBtn?.addEventListener('click', () => openModal('luckyWheelModal'));
  closeLuckyWheelBtn?.addEventListener('click', () => closeModal('luckyWheelModal'));

  spinWheelBtn?.addEventListener('click', async () => {
    if (isSpinningWheel) return;
    if (window.lastUserData?.wheel_status) {
      const ws = window.lastUserData.wheel_status;
      if (!ws.has_active_sub) {
        alert('⚠️ برای استفاده از گردونه شانس، داشتن یک اشتراک فعال در پنل الزامی است.');
        return;
      }
      if (ws.next_spin_seconds > 0) {
        alert(`⏳ گردونه هر ۲۴ ساعت یک‌بار قابل استفاده است.\nزمان باقیمانده تا شانس بعدی: ${formatCountdown(ws.next_spin_seconds)}`);
        return;
      }
    }

    isSpinningWheel = true;
    spinWheelBtn.disabled = true;
    spinWheelBtn.innerText = '...';

    let chosenPrize = null;
    let targetIndex = 0;

    try {
      const res = await window.api.spinWheel();
      if (res.ok && res.prize) {
        chosenPrize = res.prize;
        targetIndex = prizeMap[chosenPrize.id] ?? 0;
      } else if (!res.ok && res.error) {
        alert(res.error);
        isSpinningWheel = false;
        if (res.next_spin_seconds) {
          updateWheelUIState(false, true, res.next_spin_seconds);
        } else {
          spinWheelBtn.disabled = false;
          spinWheelBtn.innerText = 'بچرخون!';
        }
        return;
      }
    } catch (err) {
      console.debug('Wheel spin API offline fallback', err);
    }

    if (!chosenPrize) {
      targetIndex = Math.floor(Math.random() * localPrizes.length);
      chosenPrize = localPrizes[targetIndex];
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
      hapticFeedback('success');

      const isAgain = chosenPrize.id === 'again';
      const isBlank = chosenPrize.id === 'blank';

      if (isAgain) {
        spinWheelBtn.disabled = false;
        spinWheelBtn.innerText = 'بچرخون!';
        if (wheelResultText) wheelResultText.innerHTML = '🔄 <b>شانس مجدد!</b> گردونه دوباره برای شما فعال شد، همین الان بچرخون!';
        alert('🔄 شانس مجدد برنده شدید! می‌توانید یک‌بار دیگر بچرخانید.');
      } else {
        updateWheelUIState(false, true, 86400);
        if (isBlank) {
          if (wheelResultText) wheelResultText.innerHTML = '❌ <b>متاسفانه پوچ شد!</b> شانس بعدی شما ۲۴ ساعت دیگر فعال می‌شود.';
          alert('❌ این چرخش پوچ شد! شانس بعدی شما ۲۴ ساعت دیگر فعال خواهد شد.');
        } else if (chosenPrize.code || chosenPrize.type === 'coupon') {
          const couponCode = chosenPrize.code || 'ارسال‌شده در تلگرام';
          if (wheelResultText) {
            wheelResultText.innerHTML = `🎉 <b>تبریک!</b> شما برنده <b class="text-amber-400 font-bold">${chosenPrize.name || chosenPrize.text}</b> شدید!<br/><span class="font-mono text-cyan-400 font-bold block mt-1 select-all" dir="ltr">کد: ${couponCode}</span><span class="text-[10px] text-slate-400 block mt-0.5">⏱ مهلت استفاده: ۲۴ ساعت آینده در تب فروشگاه</span>`;
          }
          alert(`🎉 تبریک! شما برنده ${chosenPrize.name || chosenPrize.text} شدید!\nکد تخفیف: ${couponCode}\nمهلت استفاده: تا ۲۴ ساعت آینده در تب فروشگاه`);
        } else {
          if (wheelResultText) wheelResultText.innerHTML = `🎉 <b>تبریک فوق‌العاده!</b> شما برنده <b class="text-emerald-400 font-bold">${chosenPrize.name || chosenPrize.text}</b> شدید!`;
          alert(`🎉 تبریک! شما برنده ${chosenPrize.name || chosenPrize.text} شدید! جایزه با موفقیت ثبت شد.`);
        }
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      }
    }, 3650);
  });
}

window.updateWheelUIState = updateWheelUIState;
window.setupLuckyWheel = setupLuckyWheel;

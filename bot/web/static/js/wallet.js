/**
 * RemnaStore Pro - Wallet & Topup Logic
 */

let currentTopupInvoice = null;

function renderWalletTransactions(transactions) {
  const txContainer = document.getElementById('walletTransactionsList');
  if (!txContainer) return;

  const txList = transactions || [];
  if (txList.length === 0) {
    txContainer.innerHTML = `
      <div class="p-4 rounded-xl bg-transparent border border-slate-700/50 text-center text-xs text-slate-400">
        <span>🧾 هنوز تراکنش یا سفارشی برای این حساب ثبت نشده است.</span>
      </div>
    `;
    return;
  }

  txContainer.innerHTML = txList.map(tx => `
    <div class="bg-transparent rounded-xl p-3 border border-slate-700/60 flex items-center justify-between text-xs">
      <div class="flex items-center gap-2.5">
        <span class="text-xl">${tx.type === 'topup' ? '💳' : '🛒'}</span>
        <div>
          <span class="font-bold text-slate-200 block">${tx.title}</span>
          <span class="text-[10px] text-slate-400 font-mono mt-0.5" dir="ltr">${toEnglishDigits(tx.date_jalali || '')}</span>
        </div>
      </div>
      <div class="text-left space-y-0.5">
        <div class="inline-flex items-center gap-1 font-bold ${tx.is_positive ? 'text-emerald-400' : 'text-slate-200'}" dir="rtl">
          <span class="font-mono text-xs" dir="ltr">${Number(tx.amount != null ? tx.amount : 0).toLocaleString('en-US')}</span>
          <span class="font-mono text-sm leading-none font-bold">${tx.is_positive ? '+' : '-'}</span>
          <span class="font-sans text-[10px] text-slate-400 font-normal">تومان</span>
        </div>
        <span class="text-[10px] text-${tx.status_color || 'emerald'}-400 font-sans block">
          ${tx.status}
        </span>
      </div>
    </div>
  `).join('');
}

function updateTopupDisplays(amt) {
  const cardAmountDisplay = document.getElementById('topupCardAmountDisplay');
  if (cardAmountDisplay) {
    cardAmountDisplay.innerText = `${Number(amt || 0).toLocaleString('en-US')} تومان`;
  }
  if (window.storeSettings?.ton_rate_toman && window.storeSettings.ton_rate_toman > 0) {
    const tonAmt = ((amt || 0) / window.storeSettings.ton_rate_toman).toFixed(4);
    const cryptoTonEl = document.getElementById('cryptoAmountTon');
    if (cryptoTonEl) cryptoTonEl.innerText = `${tonAmt} TON`;
  }
}

async function loadTopupInfo() {
  try {
    const res = await window.api.getTopupInfo();
    if (res.ok) {
      window.storeSettings = res;
      const cardNumEl = document.getElementById('topupCardNumber');
      const cardHolderEl = document.getElementById('topupCardHolder');
      if (cardNumEl) cardNumEl.innerText = res.card_number || 'هنوز ثبت نشده';
      if (cardHolderEl) cardHolderEl.innerText = res.card_holder || 'مدیریت سرور';
      const inputEl = document.getElementById('topupAmountInput');
      updateTopupDisplays(parseInt(inputEl?.value || '50000'));
    }
  } catch (err) {}
}

function openTopupModal(defaultAmt) {
  const amt = defaultAmt && defaultAmt >= 50000 ? defaultAmt : 50000;
  const inputEl = document.getElementById('topupAmountInput');
  if (inputEl) inputEl.value = amt;
  updateTopupDisplays(amt);
  loadTopupInfo();
  openModal('topupModal');
}

function setupWalletListeners() {
  const topupAmountInput = document.getElementById('topupAmountInput');
  topupAmountInput?.addEventListener('input', (e) => {
    updateTopupDisplays(parseInt(e.target.value || '0'));
  });

  document.querySelectorAll('.topup-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const amt = parseInt(btn.getAttribute('data-amt') || '50000');
      if (topupAmountInput) topupAmountInput.value = amt;
      updateTopupDisplays(amt);
    });
  });

  const methodCardBtn = document.getElementById('topupMethodCardBtn');
  const methodCryptoBtn = document.getElementById('topupMethodCryptoBtn');
  const cardView = document.getElementById('topupCardView');
  const cryptoView = document.getElementById('topupCryptoView');

  methodCardBtn?.addEventListener('click', () => {
    methodCardBtn.classList.replace('text-slate-400', 'text-white');
    methodCardBtn.classList.add('bg-blue-600');
    methodCryptoBtn.classList.replace('text-white', 'text-slate-400');
    methodCryptoBtn.classList.remove('bg-blue-600');
    cardView?.classList.remove('hidden');
    cryptoView?.classList.add('hidden');
  });

  methodCryptoBtn?.addEventListener('click', () => {
    methodCryptoBtn.classList.replace('text-slate-400', 'text-white');
    methodCryptoBtn.classList.add('bg-blue-600');
    methodCardBtn.classList.replace('text-white', 'text-slate-400');
    methodCardBtn.classList.remove('bg-blue-600');
    cryptoView?.classList.remove('hidden');
    cardView?.classList.add('hidden');
  });

let cryptoCountdownTimerInterval = null;

function startCryptoCountdownTimer(seconds = 1800) {
  if (cryptoCountdownTimerInterval) {
    clearInterval(cryptoCountdownTimerInterval);
    cryptoCountdownTimerInterval = null;
  }
  let remaining = seconds;
  const timerEl = document.getElementById('cryptoCountdownTimer');
  if (timerEl) {
    timerEl.classList.remove('text-rose-400', 'bg-rose-500/10', 'border-rose-500/20');
    timerEl.classList.add('text-amber-400', 'bg-amber-500/10', 'border-amber-500/20');
  }

  const updateDisplay = () => {
    if (!timerEl) return;
    if (remaining <= 0) {
      timerEl.innerText = '00:00 (منقضی شد)';
      timerEl.classList.remove('text-amber-400', 'bg-amber-500/10', 'border-amber-500/20');
      timerEl.classList.add('text-rose-400', 'bg-rose-500/10', 'border-rose-500/20');
      if (cryptoCountdownTimerInterval) clearInterval(cryptoCountdownTimerInterval);
      return;
    }
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    timerEl.innerText = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  updateDisplay();
  cryptoCountdownTimerInterval = setInterval(() => {
    remaining -= 1;
    updateDisplay();
  }, 1000);
}

function stopCryptoCountdownTimer() {
  if (cryptoCountdownTimerInterval) {
    clearInterval(cryptoCountdownTimerInterval);
    cryptoCountdownTimerInterval = null;
  }
}

  document.getElementById('closeTopupModalBtn')?.addEventListener('click', () => {
    stopCryptoCountdownTimer();
    closeModal('topupModal');
  });

  document.getElementById('chargeWalletBtn')?.addEventListener('click', () => {
    openTopupModal(50000);
  });

  const handleCopyCard = () => {
    const cardEl = document.getElementById('topupCardNumber');
    const card = cardEl?.innerText?.trim();
    if (card && !card.includes('----') && !card.includes('ثبت نشده')) {
      const cleanDigits = card.replace(/[^\d]/g, '');
      copyToClipboard(cleanDigits || card, '📋 شماره کارت در کلیپ‌بورد کپی شد.');
      hapticFeedback('success');
      const btn = document.getElementById('copyTopupCardBtn');
      if (btn) {
        btn.innerText = '✅';
        setTimeout(() => { btn.innerText = '📋'; }, 1500);
      }
    } else {
      showToast('⚠️ شماره کارتی برای کپی کردن یافت نشد.');
    }
  };

  document.getElementById('copyTopupCardBtn')?.addEventListener('click', handleCopyCard);
  document.getElementById('topupCardNumber')?.addEventListener('click', handleCopyCard);

  let selectedReceiptImageBase64 = null;
  const imageInput = document.getElementById('topupCardImageInput');
  const uploadImgBtn = document.getElementById('uploadCardReceiptImageBtn');
  const previewContainer = document.getElementById('receiptImagePreviewContainer');
  const previewImg = document.getElementById('receiptImagePreview');
  const previewName = document.getElementById('receiptImageName');
  const removeImgBtn = document.getElementById('removeReceiptImageBtn');

  uploadImgBtn?.addEventListener('click', () => {
    imageInput?.click();
  });

  imageInput?.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      showToast('⚠️ حداکثر حجم مجاز تصویر ۵ مگابایت است.');
      return;
    }
    const reader = new FileReader();
    reader.onload = (loadEvt) => {
      selectedReceiptImageBase64 = loadEvt.target.result;
      if (previewImg) previewImg.src = selectedReceiptImageBase64;
      if (previewName) previewName.innerText = file.name || 'تصویر رسید انتخاب شد';
      previewContainer?.classList.remove('hidden');
      uploadImgBtn?.classList.add('hidden');
    };
    reader.readAsDataURL(file);
  });

  removeImgBtn?.addEventListener('click', () => {
    selectedReceiptImageBase64 = null;
    if (imageInput) imageInput.value = '';
    previewContainer?.classList.add('hidden');
    uploadImgBtn?.classList.remove('hidden');
  });

  document.getElementById('submitCardTopupBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0');
    const receipt = document.getElementById('topupCardReceiptInput')?.value?.trim();
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید.');
      return;
    }
    if (!receipt && !selectedReceiptImageBase64) {
      showToast('⚠️ لطفاً کد پیگیری یا تصویر رسید واریزی را وارد فرمایید.');
      return;
    }

    const submitBtn = document.getElementById('submitCardTopupBtn');
    submitBtn.disabled = true;
    submitBtn.innerText = 'در حال ثبت...';
    try {
      const res = await window.api.submitCardTopup(amt, receipt || 'تصویر فیش پیوست شد', selectedReceiptImageBase64);
      if (res.ok) {
        showToast('✅ رسید با موفقیت ثبت شد و پس از بررسی ادمین حساب شارژ می‌گردد.');
        selectedReceiptImageBase64 = null;
        if (imageInput) imageInput.value = '';
        previewContainer?.classList.add('hidden');
        uploadImgBtn?.classList.remove('hidden');
        closeModal('topupModal');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(`❌ ${res.message || 'خطا در ثبت رسید'}`);
      }
    } catch (e) {
      showToast('❌ خطا در ارسال درخواست.');
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerText = '📤 ثبت و ارسال رسید پرداخت';
    }
  });

  document.getElementById('generateTonInvoiceBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0');
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید.');
      return;
    }
    const genBtn = document.getElementById('generateTonInvoiceBtn');
    genBtn.disabled = true;
    genBtn.innerText = 'ایجاد فاکتور...';
    try {
      const res = await window.api.createCryptoInvoice(amt);
      if (res.ok && res.invoice) {
        currentTopupInvoice = res.invoice;
        document.getElementById('cryptoInvoiceInitial')?.classList.add('hidden');
        document.getElementById('cryptoInvoiceDetails')?.classList.remove('hidden');
        document.getElementById('cryptoAmountTon').innerText = `${res.invoice.amount_ton} TON`;
        document.getElementById('cryptoPayAddress').innerText = res.invoice.pay_address;
        document.getElementById('cryptoComment').innerText = res.invoice.comment;
        const targetLink = res.invoice.universal_link || res.invoice.deep_link || '#';
        const tonBtn = document.getElementById('cryptoTonkeeperLink');
        if (tonBtn) tonBtn.href = targetLink;
        startCryptoCountdownTimer(1800);
      } else {
        showToast(`❌ ${res.message || 'خطا در ایجاد فاکتور کریپتو'}`);
      }
    } catch (e) {
      showToast('❌ خطا در برقراری ارتباط.');
    } finally {
      genBtn.disabled = false;
      genBtn.innerText = '💎 ایجاد فاکتور پرداخت TON';
    }
  });

  document.getElementById('cryptoTonkeeperLink')?.addEventListener('click', (e) => {
    e.preventDefault();
    const targetLink = currentTopupInvoice?.universal_link || currentTopupInvoice?.deep_link;
    if (targetLink) {
      if (window.Telegram?.WebApp?.openLink) {
        try {
          window.Telegram.WebApp.openLink(targetLink);
        } catch(err) {
          window.open(targetLink, '_blank');
        }
      } else {
        window.open(targetLink, '_blank');
      }
    }
  });

  document.getElementById('copyTonAmountBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.amount_ton) {
      copyToClipboard(String(currentTopupInvoice.amount_ton), '📋 مقدار TON کپی شد.');
    }
  });

  document.getElementById('copyTonAddressBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.pay_address) {
      copyToClipboard(currentTopupInvoice.pay_address, '📋 آدرس ولت TON کپی شد.');
    }
  });

  document.getElementById('copyTonCommentBtn')?.addEventListener('click', () => {
    if (currentTopupInvoice?.comment) {
      copyToClipboard(currentTopupInvoice.comment, '📋 کامنت (Memo) کپی شد.');
    }
  });

  document.getElementById('cryptoCheckStatusBtn')?.addEventListener('click', async () => {
    if (!currentTopupInvoice?.id) return;
    const chkBtn = document.getElementById('cryptoCheckStatusBtn');
    chkBtn.disabled = true;
    chkBtn.innerText = 'در حال بررسی شبکه...';
    try {
      const res = await window.api.checkCryptoInvoice(currentTopupInvoice.id);
      if (res.ok && res.paid) {
        showToast('🎉 پرداخت تایید شد و کیف پول شارژ گردید!');
        stopCryptoCountdownTimer();
        closeModal('topupModal');
        if (typeof syncUserDataWithApi === 'function') syncUserDataWithApi(window.currentAccountId);
      } else {
        showToast(res.message || 'تراکنش هنوز تایید نشده است.');
      }
    } catch (e) {
      showToast('❌ خطا در استعلام پرداخت.');
    } finally {
      chkBtn.disabled = false;
      chkBtn.innerText = '🔄 بررسی وضعیت پرداخت';
    }
  });
}

window.renderWalletTransactions = renderWalletTransactions;
window.openTopupModal = openTopupModal;
window.setupWalletListeners = setupWalletListeners;

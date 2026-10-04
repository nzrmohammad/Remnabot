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
      <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-700/50 text-center text-xs text-slate-400">
        <span>🧾 هنوز تراکنش یا سفارشی برای این حساب ثبت نشده است.</span>
      </div>
    `;
    return;
  }

  txContainer.innerHTML = txList.map(tx => `
    <div class="bg-slate-900/70 rounded-xl p-3 border border-slate-700/60 flex items-center justify-between text-xs">
      <div class="flex items-center gap-2.5">
        <span class="text-xl">${tx.type === 'topup' ? '💳' : '🛒'}</span>
        <div>
          <span class="font-bold text-slate-200 block">${tx.title}</span>
          <span class="text-[10px] text-slate-400 font-mono mt-0.5" dir="ltr">${tx.date_jalali || ''}</span>
        </div>
      </div>
      <div class="text-left font-mono">
        <span class="font-bold ${tx.is_positive ? 'text-emerald-400' : 'text-slate-200'} block" dir="ltr">
          ${(tx.amount != null ? Number(tx.amount).toLocaleString('en-US') : '0')}${tx.is_positive ? '+' : '-'} تومان
        </span>
        <span class="text-[10px] text-${tx.status_color || 'emerald'}-400 font-sans">
          ${tx.status}
        </span>
      </div>
    </div>
  `).join('');
}

function updateTopupDisplays(amt) {
  const cardAmountDisplay = document.getElementById('topupCardAmountDisplay');
  if (cardAmountDisplay) {
    cardAmountDisplay.innerText = `${(amt || 0).toLocaleString('fa-IR')} تومان`;
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

  document.getElementById('closeTopupModalBtn')?.addEventListener('click', () => {
    closeModal('topupModal');
  });

  document.getElementById('chargeWalletBtn')?.addEventListener('click', () => {
    openTopupModal(50000);
  });

  document.getElementById('copyTopupCardBtn')?.addEventListener('click', () => {
    const card = document.getElementById('topupCardNumber')?.innerText;
    if (card && !card.includes('-')) {
      copyToClipboard(card.replace(/\s+/g, ''), '📋 شماره کارت کپی شد.');
    }
  });

  document.getElementById('submitCardTopupBtn')?.addEventListener('click', async () => {
    const amt = parseInt(topupAmountInput?.value || '0');
    const receipt = document.getElementById('topupCardReceiptInput')?.value?.trim();
    if (!amt || amt < 10000) {
      showToast('⚠️ لطفاً مبلغ معتبر وارد فرمایید.');
      return;
    }
    if (!receipt) {
      showToast('⚠️ لطفاً کد پیگیری یا شماره ارجاع فیش واریزی را وارد فرمایید.');
      return;
    }

    const submitBtn = document.getElementById('submitCardTopupBtn');
    submitBtn.disabled = true;
    submitBtn.innerText = 'در حال ثبت...';
    try {
      const res = await window.api.submitCardTopup(amt, receipt);
      if (res.ok) {
        showToast('✅ رسید با موفقیت ثبت شد و پس از بررسی ادمین حساب شارژ می‌گردد.');
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
        document.getElementById('cryptoTonkeeperLink').href = res.invoice.deep_link;
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

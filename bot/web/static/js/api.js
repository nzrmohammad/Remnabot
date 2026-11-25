/**
 * RemnaStore Pro - Centralized API Client
 * Eliminates repetitive fetch headers, initData injection, and error handling.
 */

const api = {
  _lastSessionExpiredAt: 0,

  notifySessionExpired() {
    const now = Date.now();
    if (now - this._lastSessionExpiredAt < 15000) return;
    this._lastSessionExpiredAt = now;

    if (typeof document !== 'undefined' && document.body && !document.getElementById('tmaSessionExpiredBanner')) {
      const banner = document.createElement('div');
      banner.id = 'tmaSessionExpiredBanner';
      banner.dir = 'rtl';
      banner.className = 'fixed top-4 left-4 right-4 z-[100] modal-card t-main border border-rose-500/30 rounded-2xl p-3.5 shadow-2xl flex items-center justify-between gap-3 max-w-lg mx-auto';

      const textWrap = document.createElement('div');
      textWrap.className = 'text-xs leading-relaxed font-semibold';
      textWrap.textContent = 'نشست کاربری تلگرام منقضی شده است. لطفاً صفحه را بارگذاری مجدد کنید.';

      const actions = document.createElement('div');
      actions.className = 'flex items-center gap-2 shrink-0';

      const reloadBtn = document.createElement('button');
      reloadBtn.type = 'button';
      reloadBtn.className = 'btn btn-primary text-xs px-3 py-1.5 rounded-xl';
      reloadBtn.textContent = 'بارگذاری مجدد';
      reloadBtn.addEventListener('click', () => {
        window.location.reload();
      });

      if (window.Telegram?.WebApp?.close) {
        const tgCloseBtn = document.createElement('button');
        tgCloseBtn.type = 'button';
        tgCloseBtn.className = 'btn btn-secondary text-xs px-2.5 py-1.5 rounded-xl';
        tgCloseBtn.textContent = 'خروج';
        tgCloseBtn.addEventListener('click', () => {
          try { window.Telegram.WebApp.close(); } catch (e) { window.location.reload(); }
        });
        actions.appendChild(tgCloseBtn);
      }

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'btn btn-secondary text-xs px-2.5 py-1.5 rounded-xl';
      closeBtn.textContent = 'بستن';
      closeBtn.addEventListener('click', () => {
        banner.remove();
      });

      actions.appendChild(reloadBtn);
      actions.appendChild(closeBtn);
      banner.appendChild(textWrap);
      banner.appendChild(actions);
      document.body.appendChild(banner);
    }

    if (typeof window !== 'undefined' && typeof window.showToast === 'function') {
      window.showToast('⚠️ نشست کاربری تلگرام منقضی شد. لطفاً صفحه را مجدداً باز کنید.', 'warning', 5000);
    }
  },

  getInitData() {
    if (window.Telegram?.WebApp?.initData) {
      return window.Telegram.WebApp.initData;
    }
    const params = new URLSearchParams(window.location.search);
    const searchInit = params.get('initData');
    if (searchInit) return searchInit;
    if (window.location.hash) {
      try {
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
        const hashInit = hashParams.get('tgWebAppData');
        if (hashInit) return hashInit;
      } catch (e) {}
    }
    return '';
  },

  async request(url, options = {}) {
    const headers = {
      'X-Telegram-Init-Data': this.getInitData(),
      ...(options.headers || {}),
    };

    if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    let timeoutId = null;
    let signal = options.signal;
    const timeoutMs = options.timeout || 15000;

    if (!signal && typeof AbortController !== 'undefined') {
      const controller = new AbortController();
      timeoutId = setTimeout(() => {
        try {
          controller.abort(new Error('Request timeout'));
        } catch (e) {
          controller.abort();
        }
      }, timeoutMs);
      signal = controller.signal;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal,
      });

      let data = null;
      try {
        data = await response.json();
      } catch (e) {
        data = null;
      }

      if (data && typeof data === 'object') {
        data._status = response.status;
        data._httpOk = response.ok;
      }

      if (response.status === 401 && String(url || '').startsWith('/api/')) {
        this.notifySessionExpired();
      }
      if (!response.ok && response.status >= 500) {
        console.error('[api error]', options.method || 'GET', url, response.status, data);
      }
      return { ok: response.ok, status: response.status, data };
    } catch (netErr) {
      const isTimeout = netErr?.name === 'AbortError' || String(netErr).toLowerCase().includes('timeout');
      console.warn(`API ${isTimeout ? 'timeout' : 'network error'} for ${url}:`, netErr);
      const errMsg = isTimeout ? 'مهلت زمانی ارتباط با سرور به پایان رسید (Timeout)' : 'خطای شبکه در ارتباط با سرور';
      const fallbackData = {
        ok: false,
        status: isTimeout ? 408 : 0,
        _status: isTimeout ? 408 : 0,
        _httpOk: false,
        error: errMsg,
        is_timeout: isTimeout,
      };
      return { ok: false, status: fallbackData.status, data: fallbackData };
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
  },

  async getBlob(url, options = {}) {
    const headers = {
      'X-Telegram-Init-Data': this.getInitData(),
      ...(options.headers || {}),
    };
    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      if (response.status === 401 && String(url || '').startsWith('/api/')) {
        this.notifySessionExpired();
      }
      const err = new Error(`HTTP error ${response.status}`);
      err.status = response.status;
      throw err;
    }
    return response.blob();
  },

  async get(url, queryParams = {}, options = {}) {
    const searchParams = new URLSearchParams(queryParams);
    const locParams = new URLSearchParams(window.location.search);
    for (const key of ['dev_id', 'user_id']) {
      if (locParams.has(key) && !searchParams.has(key)) {
        searchParams.set(key, locParams.get(key));
      }
    }
    const qs = searchParams.toString();
    const fullUrl = qs ? `${url}?${qs}` : url;
    const res = await this.request(fullUrl, { method: 'GET', ...options });
    const data = res.data || {};
    data._status = res.status;
    data._httpOk = res.ok;
    return data;
  },

  async post(url, body = {}, options = {}) {
    let fullUrl = url;
    const locParams = new URLSearchParams(window.location.search);
    const forwardParams = new URLSearchParams();
    for (const key of ['dev_id', 'user_id']) {
      if (locParams.has(key)) {
        forwardParams.set(key, locParams.get(key));
      }
    }
    const qs = forwardParams.toString();
    if (qs && !fullUrl.includes('?')) {
      fullUrl = `${fullUrl}?${qs}`;
    }
    const res = await this.request(fullUrl, { method: 'POST', body, ...options });
    const data = res.data || {};
    data._status = res.status;
    data._httpOk = res.ok;
    return data;
  },

  // Specific Domain Endpoints
  async getMe(accountId = null, options = {}) {
    let url = '/api/user/me' + (window.location.search || '');
    if (accountId) {
      url += (url.includes('?') ? '&' : '?') + `account_id=${accountId}`;
    }
    if (options.refresh) {
      url += (url.includes('?') ? '&' : '?') + 'refresh=1';
    }
    const res = await this.request(url, { method: 'GET', ...options });
    const data = res.data || {};
    data._status = res.status;
    data._httpOk = res.ok;
    return data;
  },

  async revokeSub(accountId = null) {
    const acc = accountId || window.currentAccountId;
    const payload = acc ? { account_id: acc } : {};
    return this.post('/api/user/revoke_sub', payload);
  },

  async killDevice(hwid) {
    return this.post('/api/user/kill_device', { hwid });
  },

  async validateCoupon(code) {
    return this.post('/api/user/validate_coupon', { code });
  },

  async redeemVoucher(code) {
    return this.post('/api/user/wallet/redeem-voucher', { code });
  },

  async setAutoRenew(auto_renew) {
    return this.post('/api/user/auto-renew', { auto_renew });
  },

  async purchase(service_id, coupon_code = null, account_id = null, create_new = false, custom_username = null) {
    const payload = {
      service_id,
      coupon_code,
      account_id,
      create_new,
    };
    if (custom_username) payload.custom_username = custom_username;
    return this.post('/api/user/purchase', payload);
  },

  async createGift(data) {
    return this.post('/api/user/gift/create', data);
  },

  async claimGift(code) {
    return this.post('/api/user/gift/claim', { code });
  },

  async getGiftsHistory() {
    return this.get('/api/user/gifts');
  },

  async getInvoice(orderId, type = '') {
    const q = type ? `?type=${encodeURIComponent(type)}` : '';
    return this.get(`/api/user/invoice/${orderId}${q}`);
  },

  async sendInvoiceToTelegram(orderId, type = '', imageBase64 = null) {
    const q = type ? `?type=${encodeURIComponent(type)}` : '';
    const body = imageBase64 ? { image_base64: imageBase64 } : {};
    return this.post(`/api/user/invoice/${orderId}/send-telegram${q}`, body);
  },

  async calculateCustomPlan(traffic_gb, duration_days, hwid_limit = 2) {
    return this.post('/api/user/custom-plan/calculate', { traffic_gb, duration_days, hwid_limit });
  },

  async purchaseCustomPlan(traffic_gb, duration_days, account_id = null, hwid_limit = 2, create_new = false, custom_username = null) {
    const payload = {
      traffic_gb,
      duration_days,
      account_id,
      hwid_limit,
      create_new,
    };
    if (custom_username) payload.custom_username = custom_username;
    return this.post('/api/user/custom-plan/purchase', payload);
  },

  async getTopupInfo(options = {}) {
    const qs = options?.refresh ? '?refresh=1' : '';
    return this.get(`/api/user/topup_info${qs}`);
  },

  async submitCardTopup(amount, receipt_text, receipt_image = null) {
    return this.post('/api/user/topup/card', { amount, receipt_text, receipt_image });
  },

  async createCardAutoInvoice(amount) {
    return this.post('/api/user/topup/card-auto/create', { amount });
  },

  async getCardAutoStatus(uuid = null) {
    return this.get('/api/user/topup/card-auto/status' + (uuid ? `?uuid=${encodeURIComponent(uuid)}` : ''));
  },

  async cancelCardAutoInvoice(uuid) {
    return this.post('/api/user/topup/card-auto/cancel', { uuid });
  },

  async createCryptoInvoice(amount) {
    return this.post('/api/user/topup/crypto', { amount });
  },

  async checkCryptoInvoice(invoice_id) {
    return this.post('/api/user/topup/crypto/check', { invoice_id });
  },

  async createStarsInvoice(amount) {
    return this.post('/api/user/topup/stars', { amount });
  },

  async createTrxInvoice(amount) {
    return this.post('/api/user/topup/trx', { amount });
  },

  async verifyTrxInvoice(invoice_id, tx_hash) {
    return this.post('/api/user/topup/trx/verify', { invoice_id, tx_hash });
  },

  async createPolInvoice(amount) {
    return this.post('/api/user/topup/pol', { amount });
  },

  async verifyPolInvoice(invoice_id, tx_hash) {
    return this.post('/api/user/topup/pol/verify', { invoice_id, tx_hash });
  },

  async submitTonConnectInvoice(invoice_id, tx_hash) {
    return this.post('/api/user/topup/crypto/tonconnect_submit', { invoice_id, tx_hash });
  },

  async getActiveCryptoInvoice() {
    return this.get('/api/user/topup/crypto/active');
  },

  async cancelCryptoInvoice(invoice_id) {
    return this.post('/api/user/topup/crypto/cancel', { invoice_id });
  },


  async saveSetting(key, value) {
    return this.post('/api/user/settings', { key, value });
  },

  async setBirthday(birth_date) {
    return this.post('/api/user/set_birthday', { birth_date });
  },

  async changeLanguage(language) {
    return this.post('/api/user/settings', { language });
  },

  async spinWheel(payload = {}) {
    return this.post('/api/user/spin', payload);
  },

  async claimEasterEgg() {
    return this.post('/api/user/easter-egg', {});
  },

  async getNodes() {
    return this.get(`/api/user/nodes?t=${Date.now()}`);
  },

  async getIpInfo() {
    return this.get('/api/user/ip_info');
  },

  async getSupportMessages() {
    return this.get('/api/user/support/messages');
  },

  async sendSupportMessage(text) {
    return this.post('/api/user/support/messages', { text });
  },

  async getSubscriptionConfigs(accountId = null) {
    const params = {};
    if (accountId) {
      params.account_id = accountId;
    }
    return this.get('/api/user/subscription/configs', params);
  },

  // Admin Suite Endpoints
  async getAdminOverview(params = {}) {
    return this.get('/api/admin/overview', params);
  },

  async getAdminUsers(params = {}) {
    return this.get('/api/admin/users', params);
  },

  async createAdminUser(payload) {
    return this.post('/api/admin/users/create', payload);
  },

  async checkAdminUsername(username) {
    return this.get('/api/admin/user/check_username', { username });
  },

  async getAdminInternalSquads() {
    return this.get('/api/admin/internal-squads');
  },

  async modifyUser(telegram_id, actionOrPayload, amount) {
    if (typeof actionOrPayload === 'object' && actionOrPayload !== null) {
      return this.post('/api/admin/user/modify', { telegram_id, ...actionOrPayload });
    }
    return this.post('/api/admin/user/modify', { telegram_id, action: actionOrPayload, amount });
  },

  async killUserSessions(telegram_id) {
    return this.post('/api/admin/user/kill_sessions', { telegram_id });
  },

  async toggleUserBan(telegram_id, ban) {
    return this.post('/api/admin/user/toggle_ban', { telegram_id, ban });
  },

  async updateAdminUserProfile(payload) {
    return this.post('/api/admin/user/profile', payload);
  },

  async getAdminTopups() {
    return this.get('/api/admin/topups');
  },

  async handleTopupAction(topup_id, approved) {
    return this.post('/api/admin/topup/action', { topup_id, approved });
  },

  async replyDirectTicket(telegram_id, reply_text) {
    return this.post('/api/admin/ticket/reply', { telegram_id, reply_text });
  },

  async getAdminTicketThreads() {
    return this.get('/api/admin/tickets/threads');
  },

  async getAdminTicketMessages(telegram_id) {
    return this.get('/api/admin/tickets/messages', { telegram_id });
  },

  async getAdminSettings() {
    return this.get('/api/admin/settings');
  },

  async saveAdminSettings(data) {
    return this.post('/api/admin/settings', data);
  },

  async uploadStoreLogo(logo_image) {
    return this.post('/api/admin/settings/upload-logo', { logo_image });
  },

  async broadcastMessage(message, target = 'all', photo = '') {
    return this.post('/api/admin/broadcast', { message, target, photo });
  },

  async getBroadcastStatus(broadcastId) {
    return this.get('/api/admin/broadcast/status', { id: broadcastId });
  },

  async resetUserTrial(telegram_id) {
    return this.post('/api/admin/user/reset_trial', { telegram_id });
  },

  async modifyUserWallet(telegram_id, amount, reason) {
    return this.post('/api/admin/user/wallet', { telegram_id, amount, reason });
  },

  async revokeUserSub(telegram_id) {
    return this.post('/api/admin/user/revoke_sub', { telegram_id });
  },

  async getUserHwidDevices(telegram_id, user_id = null) {
    const params = { telegram_id };
    if (user_id) params.user_id = user_id;
    return this.get('/api/admin/user/hwid_devices', params);
  },

  async deleteUserHwid(telegram_id, hwid) {
    return this.post('/api/admin/user/delete_hwid', { telegram_id, hwid });
  },

  async getAdminPlans() {
    return this.get('/api/admin/plans');
  },

  async getAdminRemnawaveSquads() {
    return this.get('/api/admin/remnawave/squads');
  },

  async saveAdminPlan(data) {
    return this.post('/api/admin/plan/save', data);
  },

  async reorderAdminPlans(plan_ids) {
    return this.post('/api/admin/plan/reorder', { plan_ids });
  },

  async toggleAdminPlan(id, is_active) {
    return this.post('/api/admin/plan/toggle', { id, is_active });
  },

  async deleteAdminPlan(id) {
    return this.post('/api/admin/plan/delete', { id });
  },

  async getAdminCoupons() {
    return this.get('/api/admin/coupons');
  },

  async getAdminCouponUsages(id) {
    return this.get(`/api/admin/coupons/${id}/usages`);
  },

  async saveAdminCoupon(data) {
    return this.post('/api/admin/coupon/save', data);
  },

  async toggleAdminCoupon(id, is_active) {
    return this.post('/api/admin/coupon/toggle', { id, is_active });
  },

  async deleteAdminCoupon(id) {
    return this.post('/api/admin/coupon/delete', { id });
  },

  async batchGenerateVouchers(data) {
    return this.post('/api/admin/coupons/batch-generate', data);
  },

  async getAdminCryptoRates(force = false) {
    return this.get('/api/admin/crypto/rates' + (force ? '?force=1' : ''));
  },

  async getSessionsExplorer() {
    return this.get('/api/admin/sessions-explorer');
  },

  async getUserLiveSessions(telegram_id) {
    return this.get(`/api/admin/user/sessions?telegram_id=${telegram_id}`);
  },

  async getUserSrh(params) {
    return this.get('/api/admin/user/srh', params);
  },

  async bulkUsersAction(data) {
    return this.post('/api/admin/users/bulk-action', data);
  },

  async getInfraBilling() {
    return this.get('/api/admin/infra/billing');
  },

  async getInfraProviders() {
    return this.get('/api/admin/infra/providers');
  },

  async saveNodeCost(data) {
    return this.post('/api/admin/infra/node-cost', data);
  },

  async restartNode(node_uuid, force_restart = false) {
    return this.post('/api/admin/infra/node/restart', { node_uuid, force_restart: Boolean(force_restart) });
  },

  async runNodeAction(action, node_uuid = '', node_name = '', force_restart = false) {
    return this.post('/api/admin/infra/node/action', {
      action,
      node_uuid,
      node_name,
      force_restart: Boolean(force_restart),
    });
  },

  async saveInfraProvider(data) {
    return this.post('/api/admin/infra/providers/save', data);
  },

  async deleteInfraProvider(uuid) {
    return this.post('/api/admin/infra/providers/delete', { uuid });
  },

  async syncInfraNodeBilling(node_uuid, provider_uuid, due_date = '') {
    return this.post('/api/admin/infra/node/sync', { node_uuid, provider_uuid, due_date });
  },

  async createInfraBill(data) {
    return this.post('/api/admin/infra/bills/create', data);
  },

  async deleteInfraBill(uuid) {
    return this.post('/api/admin/infra/bills/delete', { uuid });
  },

  async getPanelControlOverview() {
    return this.get('/api/admin/panel/control');
  },

  async savePanelHost(data) {
    return this.post('/api/admin/panel/hosts/save', data);
  },

  async bulkPanelHosts(action, uuids) {
    return this.post('/api/admin/panel/hosts/bulk', { action, uuids });
  },

  async savePanelSnippet(name, snippet, is_edit = false) {
    return this.post('/api/admin/panel/snippets/save', { name, snippet, is_edit: Boolean(is_edit) });
  },

  async deletePanelSnippet(name) {
    return this.post('/api/admin/panel/snippets/delete', { name });
  },

  async savePanelSubSettings(data) {
    return this.post('/api/admin/panel/subscription-settings', data);
  },

  async updateExternalSquadUsers(squad_uuid, user_uuids, action = 'add') {
    return this.post('/api/admin/panel/external-squads/users', { squad_uuid, user_uuids, action });
  },

  async createPanelApiToken(token_name) {
    return this.post('/api/admin/panel/tokens/create', { token_name });
  },

  async deletePanelApiToken(uuid) {
    return this.post('/api/admin/panel/tokens/delete', { uuid });
  },

  async getSslHealth() {
    return this.get('/api/admin/infra/ssl-health');
  },

  async checkDomainSsl(domain) {
    return this.post('/api/admin/infra/ssl-check', { domain });
  },

  async addCustomSslDomain(domain) {
    return this.post('/api/admin/infra/ssl-domains/add', { domain });
  },

  async deleteCustomSslDomain(domain) {
    return this.post('/api/admin/infra/ssl-domains/delete', { domain });
  },

  async getGithubReleases(appId = '') {
    const query = appId ? `?app_id=${encodeURIComponent(appId)}` : '';
    return this.get(`/api/admin/infra/github-releases${query}`);
  },

  async getAdminCampaigns() {
    return this.get('/api/admin/campaigns');
  },

  async createAdminCampaign(data) {
    return this.post('/api/admin/campaign/create', data);
  },

  async deleteAdminCampaign(id) {
    return this.post('/api/admin/campaign/delete', { id });
  },

  async runCheckHost(data) {
    return this.post('/api/admin/tools/check-host', data);
  },

  async getAsnPrefixes(asn) {
    return this.get(`/api/admin/tools/asn-prefixes?asn=${encodeURIComponent(asn)}`);
  },

  async getSystemHealth(forceRefresh = false) {
    return this.get('/api/admin/system-health' + (forceRefresh ? '?refresh=1' : ''));
  },

  async runAdminReconcile() {
    return this.post('/api/admin/reconcile/run', {});
  },

  haptic(type = 'success') {
    if (typeof window.hapticFeedback === 'function') {
      window.hapticFeedback(type);
    } else if (window.Telegram?.WebApp?.HapticFeedback) {
      try {
        if (type === 'impact') {
          window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
        } else if (type === 'light') {
          window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
        } else if (type === 'selection') {
          window.Telegram.WebApp.HapticFeedback.selectionChanged();
        } else {
          window.Telegram.WebApp.HapticFeedback.notificationOccurred(type);
        }
      } catch (e) {}
    }
  },
};

window.api = api;
window.api.admin = api;


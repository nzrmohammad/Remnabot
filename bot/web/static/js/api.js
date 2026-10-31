/**
 * RemnaStore Pro - Centralized API Client
 * Eliminates repetitive fetch headers, initData injection, and error handling.
 */

const api = {
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
      const err = new Error(`HTTP error ${response.status}`);
      err.status = response.status;
      throw err;
    }
    return response.blob();
  },

  async get(url, queryParams = {}, options = {}) {
    const searchParams = new URLSearchParams(queryParams);
    const locParams = new URLSearchParams(window.location.search);
    for (const key of ['dev_id', 'user_id', 'initData']) {
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
    for (const key of ['dev_id', 'user_id', 'initData']) {
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
    const res = await this.request(url, { method: 'GET', ...options });
    const data = res.data || {};
    data._status = res.status;
    data._httpOk = res.ok;
    return data;
  },

  async revokeSub() {
    return this.post('/api/user/revoke_sub');
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

  async purchase(service_id, coupon_code = null, account_id = null) {
    return this.post('/api/user/purchase', {
      service_id,
      coupon_code,
      account_id,
    });
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

  async getInvoice(orderId) {
    return this.get(`/api/user/invoice/${orderId}`);
  },

  async sendInvoiceToTelegram(orderId) {
    return this.post(`/api/user/invoice/${orderId}/send-telegram`, {});
  },

  async calculateCustomPlan(traffic_gb, duration_days) {
    return this.post('/api/user/custom-plan/calculate', { traffic_gb, duration_days });
  },

  async purchaseCustomPlan(traffic_gb, duration_days, account_id = null) {
    return this.post('/api/user/custom-plan/purchase', { traffic_gb, duration_days, account_id });
  },

  async getTopupInfo() {
    return this.get('/api/user/topup_info');
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

  async submitTonConnectInvoice(invoice_id, tx_hash) {
    return this.post('/api/user/topup/crypto/tonconnect_submit', { invoice_id, tx_hash });
  },

  async createXRocketInvoice(amount, currency = 'USDT') {
    return this.post('/api/user/topup/xrocket', { amount, currency });
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

  async getSubscriptionConfigs(accountId = null, subUrl = null) {
    const params = {};
    if (accountId) {
      params.account_id = accountId;
    }
    if (subUrl) {
      params.sub_url = subUrl;
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

  async broadcastMessage(message, target = 'all') {
    return this.post('/api/admin/broadcast', { message, target });
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

  async saveNodeCost(data) {
    return this.post('/api/admin/infra/node-cost', data);
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


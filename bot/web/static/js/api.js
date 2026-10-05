/**
 * RemnaStore Pro - Centralized API Client
 * Eliminates repetitive fetch headers, initData injection, and error handling.
 */

const api = {
  getInitData() {
    return window.Telegram?.WebApp?.initData || '';
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

    const response = await fetch(url, {
      ...options,
      headers,
    });

    try {
      const data = await response.json();
      return { ok: response.ok, status: response.status, data };
    } catch (e) {
      return { ok: response.ok, status: response.status, data: null };
    }
  },

  async get(url, queryParams = {}) {
    const searchParams = new URLSearchParams(queryParams);
    const qs = searchParams.toString();
    const fullUrl = qs ? `${url}?${qs}` : url;
    const res = await this.request(fullUrl, { method: 'GET' });
    return res.data || {};
  },

  async post(url, body = {}) {
    const res = await this.request(url, { method: 'POST', body });
    return res.data || {};
  },

  // Specific Domain Endpoints
  async getMe(accountId = null) {
    let url = '/api/user/me' + (window.location.search || '');
    if (accountId) {
      url += (url.includes('?') ? '&' : '?') + `account_id=${accountId}`;
    }
    const res = await this.request(url, { method: 'GET' });
    return res.data || {};
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

  async purchase(service_id, coupon_code = null, account_id = null) {
    return this.post('/api/user/purchase', {
      service_id,
      coupon_code,
      account_id,
    });
  },

  async getTopupInfo() {
    return this.get('/api/user/topup_info');
  },

  async submitCardTopup(amount, receipt_text) {
    return this.post('/api/user/topup/card', { amount, receipt_text });
  },

  async createCryptoInvoice(amount) {
    return this.post('/api/user/topup/crypto', { amount });
  },

  async checkCryptoInvoice(invoice_id) {
    return this.post('/api/user/topup/crypto/check', { invoice_id });
  },

  async saveSetting(key, value) {
    return this.post('/api/user/settings', { key, value });
  },

  async changeLanguage(language) {
    return this.post('/api/user/settings', { language });
  },

  async spinWheel() {
    return this.post('/api/user/spin');
  },

  async getNodes() {
    return this.get(`/api/user/nodes?t=${Date.now()}`);
  },

  async getIpInfo() {
    return this.get('/api/user/ip_info');
  },

  // Admin Suite Endpoints
  async getAdminOverview(params = {}) {
    return this.get('/api/admin/overview', params);
  },

  async getAdminUsers(params = {}) {
    return this.get('/api/admin/users', params);
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

  async getUserHwidDevices(telegram_id) {
    return this.get('/api/admin/user/hwid_devices', { telegram_id });
  },

  async deleteUserHwid(telegram_id, hwid) {
    return this.post('/api/admin/user/delete_hwid', { telegram_id, hwid });
  },

  async getAdminPlans() {
    return this.get('/api/admin/plans');
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
};

window.api = api;

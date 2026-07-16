// MARJA — юнит-экономика для маркетплейсов (Alpine.js)

function app() {
  return {
    // ---- Auth ----
    token: localStorage.getItem('token') || null,
    me: null,
    authMode: 'login',  // login | register | forgot | reset
    authForm: {email:'', password:'', name:'', workspace_name:'Мой магазин'},
    authError: '',
    authInfo: '',  // сообщение об успехе (напр. «письмо отправлено»)
    resetToken: '',   // из query ?reset_token=
    resetPassword2: '',  // подтверждение

    // ---- Workspaces ----
    workspaces: [],
    currentWs: null,
    newWsName: '',
    showNewWs: false,
    currentMp: 'ya_market',

    // ---- Каталог ----
    skus: [],
    categories: [],
    results: [],
    summary: {},

    // ---- Настройки ----
    storeSettings: {},
    taxSystems: {},
    acquiringOptions: {},
    showSettings: false,

    // ---- Marketplace API ----
    mpAccounts: [],
    mpForm: {api_token:'', business_id:null, campaign_id:null, label:''},
    showYaMarket: false,

    // ---- UI: юнитка ----
    filter: '',
    onlyWithCost: false,
    onlyInStock: false,
    marginFilter: 'all',   // all | good | mid | bad
    sortField: null,
    sortDir: 'asc',
    importing: false,
    syncingStocks: false,
    uploadingCosts: false,
    toast: {text:''},

    // ---- UI: вкладки ----
    activeTab: 'catalog',  // catalog | fin

    // ---- Финотчёт ----
    fin: {
      dateFrom: '',
      dateTo: '',
      source: 'key_indicators',
      report: null,
      loading: false,
      polling: false,
      lastReports: [],
    },

    // ============ init ============
    async init() {
      // По умолчанию: последние 4 недели
      const today = new Date();
      const from = new Date(today); from.setDate(today.getDate() - 27);
      this.fin.dateTo = today.toISOString().slice(0, 10);
      this.fin.dateFrom = from.toISOString().slice(0, 10);

      // Обработка ссылки сброса пароля ?reset_token=XXX
      const params = new URLSearchParams(window.location.search);
      const rt = params.get('reset_token');
      if (rt) {
        this.resetToken = rt;
        this.authMode = 'reset';
        // Убираем токен из URL, чтобы не остался в history/логах
        history.replaceState({}, '', window.location.pathname);
      }

      if (this.token) await this.afterLogin();
    },

    // ============ API helper ============
    async api(method, url, body) {
      const opts = {method, headers:{'Content-Type':'application/json'}};
      if (this.token) opts.headers['Authorization'] = 'Bearer ' + this.token;
      if (body !== undefined) opts.body = JSON.stringify(body);
      const r = await fetch(url, opts);
      if (r.status === 401) { this.logout(); throw new Error('Не авторизован'); }
      if (!r.ok) {
        const t = await r.text();
        let msg = t;
        try { msg = JSON.parse(t).detail || t; } catch(e){}
        throw new Error(msg);
      }
      if (r.status === 204) return null;
      return r.json();
    },

    async apiUpload(url, formData) {
      const opts = {method:'POST', body: formData, headers:{}};
      if (this.token) opts.headers['Authorization'] = 'Bearer ' + this.token;
      const r = await fetch(url, opts);
      if (r.status === 401) { this.logout(); throw new Error('Не авторизован'); }
      if (!r.ok) {
        const t = await r.text();
        let msg = t; try { msg = JSON.parse(t).detail || t; } catch(e){}
        throw new Error(msg);
      }
      return r.json();
    },

    // ============ Auth ============
    async doAuth() {
      this.authError = '';
      this.authInfo = '';
      try {
        const url = this.authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
        const r = await this.api('POST', url, this.authForm);
        this.token = r.access_token;
        localStorage.setItem('token', this.token);
        await this.afterLogin();
      } catch(e) {
        this.authError = String(e.message || e);
      }
    },

    async doForgotPassword() {
      this.authError = '';
      this.authInfo = '';
      if (!this.authForm.email) { this.authError = 'Укажи email'; return; }
      try {
        await this.api('POST', '/api/auth/forgot-password', {email: this.authForm.email});
        this.authInfo = 'Если такой email зарегистрирован — письмо со ссылкой отправлено. Проверь почту (и папку «Спам»).';
      } catch(e) {
        this.authError = String(e.message || e);
      }
    },

    async doResetPassword() {
      this.authError = '';
      this.authInfo = '';
      if (!this.authForm.password || this.authForm.password.length < 8) {
        this.authError = 'Пароль должен быть от 8 символов';
        return;
      }
      if (this.authForm.password !== this.resetPassword2) {
        this.authError = 'Пароли не совпадают';
        return;
      }
      try {
        const r = await this.api('POST', '/api/auth/reset-password', {
          token: this.resetToken,
          password: this.authForm.password,
        });
        this.token = r.access_token;
        localStorage.setItem('token', this.token);
        this.resetToken = '';
        this.resetPassword2 = '';
        this.authForm.password = '';
        await this.afterLogin();
      } catch(e) {
        this.authError = String(e.message || e);
      }
    },

    async afterLogin() {
      try {
        this.me = await this.api('GET', '/api/auth/me');
        this.workspaces = await this.api('GET', '/api/workspaces');
        if (this.workspaces.length > 0) {
          this.currentWs = parseInt(localStorage.getItem('ws')) || this.workspaces[0].id;
          if (!this.workspaces.find(w => w.id === this.currentWs)) this.currentWs = this.workspaces[0].id;
          await this.loadWorkspaceData();
        }
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    logout() {
      this.token = null;
      this.me = null;
      this.workspaces = [];
      this.skus = [];
      this.results = [];
      this.fin.report = null;
      localStorage.removeItem('token');
      localStorage.removeItem('ws');
    },

    // ============ Workspace ============
    async createWorkspace() {
      if (!this.newWsName.trim()) return;
      const w = await this.api('POST', '/api/workspaces', {name: this.newWsName.trim()});
      this.workspaces.push(w);
      this.currentWs = w.id;
      this.newWsName = '';
      this.showNewWs = false;
      await this.loadWorkspaceData();
      this.showToast('Магазин создан');
    },

    async loadWorkspaceData() {
      if (!this.currentWs) return;
      localStorage.setItem('ws', this.currentWs);
      try {
        const base = `/api/workspaces/${this.currentWs}`;
        [this.categories, this.storeSettings, this.mpAccounts, this.taxSystems, this.acquiringOptions] = await Promise.all([
          this.api('GET', `${base}/categories`),
          this.api('GET', `${base}/settings`),
          this.api('GET', `${base}/marketplace-accounts`),
          this.api('GET', `${base}/settings/tax-systems`),
          this.api('GET', `${base}/settings/acquiring-options`),
        ]);
        await this.recalc();
        await this.loadFinReports();
      } catch(e) { this.showToast('Ошибка загрузки: ' + e.message); }
    },

    // ============ Settings ============
    async saveSettings(field, value) {
      try {
        const s = await this.api('PATCH', `/api/workspaces/${this.currentWs}/settings`, {[field]: value});
        this.storeSettings = s;
        await this.recalc();
        this.showToast('Сохранено');
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    // ============ SKU CRUD ============
    async addRow() {
      const sku = prompt('Введи SKU (артикул):');
      if (!sku || !sku.trim()) return;
      try {
        const cat = this.categories[0]?.name || 'Товары для дома (общ)';
        await this.api('POST', `/api/workspaces/${this.currentWs}/skus`, {
          sku: sku.trim(), name: '', category: cat, model: 'FBS',
          length_cm: 0, width_cm: 0, height_cm: 0, weight_kg: 0,
          price_rub: 0, cost_rub: 0,
        });
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async saveRow(row) {
      try {
        await this.api('PATCH', `/api/workspaces/${this.currentWs}/skus/${row.id}`, {
          name: row.name, category: row.category, model: row.model,
          length_cm: row.length_cm, width_cm: row.width_cm, height_cm: row.height_cm,
          weight_kg: row.weight_kg, price_rub: row.price_rub, cost_rub: row.cost_rub,
          stock_total: row.stock_total,
        });
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async deleteRow(row) {
      if (!confirm(`Удалить SKU «${row.sku}»?`)) return;
      try {
        await this.api('DELETE', `/api/workspaces/${this.currentWs}/skus/${row.id}`);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    // ============ Calc ============
    async recalc() {
      try {
        const r = await this.api('POST', `/api/workspaces/${this.currentWs}/skus/calc`, {});
        this.results = r.results;
        this.summary = r.summary;
      } catch(e) { this.showToast('Ошибка расчёта: ' + e.message); }
    },

    // ============ Marketplace Account ============
    async saveMpAccount() {
      if (!this.mpForm.api_token) { this.showToast('Введи токен'); return; }
      try {
        await this.api('POST', `/api/workspaces/${this.currentWs}/marketplace-accounts`, {
          marketplace: 'ya_market', ...this.mpForm,
        });
        this.mpForm = {api_token:'', business_id:null, campaign_id:null, label:''};
        this.mpAccounts = await this.api('GET', `/api/workspaces/${this.currentWs}/marketplace-accounts`);
        this.showToast('Ya.Market API подключён');
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async deleteMpAccount(id) {
      if (!confirm('Удалить аккаунт?')) return;
      try {
        await this.api('DELETE', `/api/workspaces/${this.currentWs}/marketplace-accounts/${id}`);
        this.mpAccounts = await this.api('GET', `/api/workspaces/${this.currentWs}/marketplace-accounts`);
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    // ============ Ya.Market ============
    async importFromYaMarket() {
      if (this.mpAccounts.length === 0) { this.showYaMarket = true; return; }
      this.importing = true;
      try {
        const r = await this.api('POST', `/api/workspaces/${this.currentWs}/ya-market/import-offers`);
        this.showToast(`Импорт: ${r.created_in_our_db} создано, ${r.updated_in_our_db} обновлено`);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
      finally { this.importing = false; }
    },

    async syncPricesFromYaMarket() {
      this.importing = true;
      try {
        const r = await this.api('POST', `/api/workspaces/${this.currentWs}/ya-market/sync-prices`);
        this.showToast(`Цены: ${r.updated} обновлено (из ${r.matched} найденных)`);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
      finally { this.importing = false; }
    },

    async syncStocksFromYaMarket() {
      this.syncingStocks = true;
      try {
        const r = await this.api('POST', `/api/workspaces/${this.currentWs}/ya-market/sync-stocks`);
        this.showToast(`Остатки: ${r.updated} обновлено`);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
      finally { this.syncingStocks = false; }
    },

    async debugOffer() {
      const sku = prompt('SKU для проверки:');
      if (!sku) return;
      try {
        const r = await this.api('GET', `/api/workspaces/${this.currentWs}/ya-market/debug-offer?offer_id=${encodeURIComponent(sku)}`);
        alert(JSON.stringify(r, null, 2));
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async onImportCostsFile(ev) {
      const file = ev.target.files[0];
      if (!file) return;
      this.uploadingCosts = true;
      try {
        const fd = new FormData();
        fd.append('file', file);
        const r = await this.apiUpload(`/api/workspaces/${this.currentWs}/skus/import-costs`, fd);
        this.showToast(`Себест.: ${r.updated} обновлено из ${r.total} строк`);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
      finally { this.uploadingCosts = false; ev.target.value = ''; }
    },

    // ============ Финотчёт ============
    async loadFinReports() {
      try {
        const list = await this.api('GET', `/api/workspaces/${this.currentWs}/fin-report`);
        this.fin.lastReports = list || [];
        const done = (list || []).find(r => r.status === 'done');
        if (done) {
          this.fin.report = await this.api('GET', `/api/workspaces/${this.currentWs}/fin-report/${done.id}`);
        }
      } catch(e) { /* silent */ }
    },

    async generateFinReport() {
      if (!this.fin.dateFrom || !this.fin.dateTo) {
        this.showToast('Укажи даты');
        return;
      }
      if (this.mpAccounts.length === 0) {
        this.showToast('Подключи Ya.Market API');
        this.showYaMarket = true;
        return;
      }
      this.fin.loading = true;
      try {
        const r = await this.api('POST', `/api/workspaces/${this.currentWs}/fin-report/generate`, {
          date_from: this.fin.dateFrom,
          date_to: this.fin.dateTo,
          source: this.fin.source,
        });
        this.showToast('Отчёт запущен. Может занять до 3 минут…');
        await this.pollFinReport(r.report_id);
      } catch(e) {
        this.showToast('Ошибка: ' + e.message);
      } finally {
        this.fin.loading = false;
      }
    },

    async pollFinReport(reportId) {
      this.fin.polling = true;
      const started = Date.now();
      try {
        while (Date.now() - started < 4 * 60 * 1000) {
          const rep = await this.api('GET', `/api/workspaces/${this.currentWs}/fin-report/${reportId}`);
          if (rep.status === 'done') {
            this.fin.report = rep;
            await this.loadFinReports();
            this.showToast('Финотчёт готов');
            return;
          }
          if (rep.status === 'failed') {
            this.showToast('Ошибка отчёта: ' + (rep.error || 'неизвестно'));
            return;
          }
          await new Promise(res => setTimeout(res, 5000));
        }
        this.showToast('Таймаут ожидания отчёта');
      } finally { this.fin.polling = false; }
    },

    async openFinReport(id) {
      try {
        this.fin.report = await this.api('GET', `/api/workspaces/${this.currentWs}/fin-report/${id}`);
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    get finTotal() {
      if (!this.fin.report) return null;
      return this.fin.report.periods.find(p => p.period_type === 'total');
    },

    get finWeeks() {
      if (!this.fin.report) return [];
      return this.fin.report.periods
        .filter(p => p.period_type === 'week')
        .sort((a, b) => a.period_from.localeCompare(b.period_from));
    },

    finRowValue(p, key) {
      return p ? (+p[key] || 0) : 0;
    },

    // ============ Sort/Filter ============
    toggleSort(field) {
      if (this.sortField !== field) { this.sortField = field; this.sortDir = 'asc'; return; }
      if (this.sortDir === 'asc') { this.sortDir = 'desc'; return; }
      this.sortField = null; this.sortDir = 'asc';
    },

    sortArrow(field) {
      if (this.sortField !== field) return '';
      return this.sortDir === 'asc' ? ' ↑' : ' ↓';
    },

    get filteredResults() {
      let items = this.results.slice();
      if (this.filter) {
        const q = this.filter.toLowerCase();
        items = items.filter(r =>
          (r.sku||'').toLowerCase().includes(q) ||
          (r.name||'').toLowerCase().includes(q)
        );
      }
      if (this.onlyWithCost) {
        items = items.filter(r => +r.cost_rub > 0);
      }
      if (this.onlyInStock) {
        items = items.filter(r => +(r.stock_total || 0) > 0);
      }
      if (this.marginFilter === 'good') items = items.filter(r => +r.margin_pct >= 15);
      else if (this.marginFilter === 'mid') items = items.filter(r => +r.margin_pct >= 5 && +r.margin_pct < 15);
      else if (this.marginFilter === 'bad') items = items.filter(r => +r.margin_pct < 5);

      if (this.sortField) {
        const f = this.sortField, dir = this.sortDir === 'asc' ? 1 : -1;
        items.sort((a, b) => {
          const va = a[f], vb = b[f];
          if (typeof va === 'number' || typeof vb === 'number') return ((+va||0) - (+vb||0)) * dir;
          return String(va||'').localeCompare(String(vb||'')) * dir;
        });
      }
      return items;
    },

    // ============ Format ============
    fmtRub(v) {
      if (v == null || isNaN(v)) return '—';
      return Math.round(v).toLocaleString('ru-RU') + ' ₽';
    },
    fmtRub0(v) {
      const n = +v || 0;
      if (n === 0) return '0';
      return Math.round(n).toLocaleString('ru-RU');
    },
    fmtPct(v) {
      if (v == null || isNaN(v)) return '—';
      return (+v).toFixed(1) + '%';
    },
    fmtDate(s) {
      if (!s) return '';
      const [y, m, d] = s.split('-');
      return `${d}.${m}`;
    },
    marginColor(pct) {
      if (pct == null || isNaN(pct)) return 'bg-slate-100 text-slate-400';
      if (pct >= 15) return 'bg-emerald-50 text-emerald-700 border-emerald-100';
      if (pct >= 5)  return 'bg-amber-50 text-amber-700 border-amber-100';
      return 'bg-rose-50 text-rose-700 border-rose-100';
    },
    marginBg(pct) {
      if (pct == null || isNaN(pct)) return 'background:#251B45;color:#71717A';
      if (pct >= 15) return 'background:#053426;color:#10B981';
      if (pct >= 5)  return 'background:#3F2A00;color:#FCD34D';
      return 'background:#4C0519;color:#FB7185';
    },
    finMarginColor(pct) {
      const n = +pct || 0;
      if (n >= 15) return 'color:#10B981';
      if (n >= 5) return 'color:#FCD34D';
      if (n <= 0) return 'color:#FB7185';
      return 'color:#EDE9FE';
    },

    showToast(text) {
      this.toast.text = text;
      clearTimeout(this._t);
      this._t = setTimeout(() => this.toast.text = '', 3000);
    },
  }
}

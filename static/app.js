// Юнит-экономика SaaS — фронт (Alpine.js)

function app() {
  return {
    // Auth
    token: localStorage.getItem('token') || null,
    me: null,
    authMode: 'login',
    authForm: {email:'', password:'', name:'', workspace_name:'Мой магазин'},
    authError: '',

    // Workspaces
    workspaces: [],
    currentWs: null,
    newWsName: '',
    showNewWs: false,

    // Catalog
    skus: [],
    categories: [],
    results: [],
    summary: {},

    // Settings
    storeSettings: {},
    taxSystems: {},
    acquiringOptions: {},
    showSettings: false,

    // Marketplace
    mpAccounts: [],
    mpForm: {api_token:'', business_id:null, campaign_id:null, label:''},
    showYaMarket: false,

    // UI
    filter: '',
    importing: false,
    toast: {text:''},

    // ---- init ----
    async init() {
      if (this.token) await this.afterLogin();
    },

    // ---- API helper ----
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

    // ---- Auth ----
    async doAuth() {
      this.authError = '';
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
      localStorage.removeItem('token');
      localStorage.removeItem('ws');
    },

    // ---- Workspace ----
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
      } catch(e) { this.showToast('Ошибка загрузки: ' + e.message); }
    },

    // ---- Settings ----
    async saveSettings(field, value) {
      try {
        const s = await this.api('PATCH', `/api/workspaces/${this.currentWs}/settings`, {[field]: value});
        this.storeSettings = s;
        await this.recalc();
        this.showToast('Сохранено');
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    // ---- SKU CRUD ----
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

    // ---- Calc ----
    async recalc() {
      try {
        const r = await this.api('POST', `/api/workspaces/${this.currentWs}/skus/calc`, {});
        this.results = r.results;
        this.summary = r.summary;
      } catch(e) { this.showToast('Ошибка расчёта: ' + e.message); }
    },

    // ---- Ya.Market ----
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

    // ---- Filter & format ----
    get filteredResults() {
      if (!this.filter) return this.results;
      const q = this.filter.toLowerCase();
      return this.results.filter(r => (r.sku||'').toLowerCase().includes(q) || (r.name||'').toLowerCase().includes(q));
    },

    fmtRub(v) {
      if (v == null || isNaN(v)) return '—';
      return Math.round(v).toLocaleString('ru-RU') + ' ₽';
    },
    fmtPct(v) {
      if (v == null || isNaN(v)) return '—';
      return v.toFixed(1) + '%';
    },
    marginColor(pct) {
      if (pct == null || isNaN(pct)) return 'bg-slate-100 text-slate-400';
      if (pct >= 15) return 'bg-emerald-50 text-emerald-700 border-emerald-100';
      if (pct >= 5)  return 'bg-amber-50 text-amber-700 border-amber-100';
      return 'bg-rose-50 text-rose-700 border-rose-100';
    },

    showToast(text) {
      this.toast.text = text;
      clearTimeout(this._t);
      this._t = setTimeout(() => this.toast.text = '', 3000);
    },
  }
}

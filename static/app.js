// MARJA — юнит-экономика для маркетплейсов (Alpine.js)

function app() {
  return {
    token: localStorage.getItem('token') || null,
    me: null,
    authMode: 'login',
    authForm: {email:'', password:'', name:'', workspace_name:'Мой магазин'},
    authError: '',

    workspaces: [],
    currentWs: null,
    newWsName: '',
    showNewWs: false,

    currentMp: 'ya_market',

    skus: [],
    categories: [],
    results: [],

    storeSettings: {},
    taxSystems: {},
    acquiringOptions: {},
    showSettings: false,

    mpAccounts: [],
    mpForm: {api_token:'', business_id:null, campaign_id:null, label:''},
    showYaMarket: false,

    filter: '',
    onlyWithCost: localStorage.getItem('onlyWithCost') === '1',
    onlyInStock: localStorage.getItem('onlyInStock') === '1',
    marginFilter: 'all',
    sortField: null,
    sortDir: 'asc',
    importing: false,
    syncingStocks: false,
    uploadingCosts: false,
    toast: {text:''},

    async init() {
      if (this.token) await this.afterLogin();
      this.$watch('onlyWithCost', v => localStorage.setItem('onlyWithCost', v ? '1' : '0'));
      this.$watch('onlyInStock', v => localStorage.setItem('onlyInStock', v ? '1' : '0'));
    },

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

    async doAuth() {
      this.authError = '';
      try {
        const url = this.authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
        const r = await this.api('POST', url, this.authForm);
        this.token = r.access_token;
        localStorage.setItem('token', this.token);
        await this.afterLogin();
      } catch(e) { this.authError = String(e.message || e); }
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
      this.token = null; this.me = null; this.workspaces = [];
      this.skus = []; this.results = [];
      localStorage.removeItem('token'); localStorage.removeItem('ws');
    },

    async createWorkspace() {
      if (!this.newWsName.trim()) return;
      const w = await this.api('POST', '/api/workspaces', {name: this.newWsName.trim()});
      this.workspaces.push(w); this.currentWs = w.id;
      this.newWsName = ''; this.showNewWs = false;
      await this.loadWorkspaceData();
      this.showToast('Магазин создан');
    },

    async loadWorkspaceData() {
      if (!this.currentWs) return;
      localStorage.setItem('ws', this.currentWs);
      try {
        const base = '/api/workspaces/' + this.currentWs;
        [this.categories, this.storeSettings, this.mpAccounts, this.taxSystems, this.acquiringOptions] = await Promise.all([
          this.api('GET', base + '/categories'),
          this.api('GET', base + '/settings'),
          this.api('GET', base + '/marketplace-accounts'),
          this.api('GET', base + '/settings/tax-systems'),
          this.api('GET', base + '/settings/acquiring-options'),
        ]);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка загрузки: ' + e.message); }
    },

    async saveSettings(field, value) {
      try {
        const s = await this.api('PATCH', '/api/workspaces/' + this.currentWs + '/settings', {[field]: value});
        this.storeSettings = s;
        await this.recalc();
        this.showToast('Сохранено');
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async addRow() {
      const sku = prompt('Введи SKU (артикул):');
      if (!sku || !sku.trim()) return;
      try {
        const cat = this.categories[0]?.name || 'Товары для дома (общ)';
        await this.api('POST', '/api/workspaces/' + this.currentWs + '/skus', {
          sku: sku.trim(), name: '', category: cat, model: 'FBS',
          length_cm: 0, width_cm: 0, height_cm: 0, weight_kg: 0,
          price_rub: 0, cost_rub: 0, stock_total: 0,
        });
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async saveRow(row) {
      try {
        await this.api('PATCH', '/api/workspaces/' + this.currentWs + '/skus/' + row.id, {
          name: row.name, category: row.category, model: row.model,
          length_cm: row.length_cm, width_cm: row.width_cm, height_cm: row.height_cm,
          weight_kg: row.weight_kg, price_rub: row.price_rub, cost_rub: row.cost_rub,
          stock_total: row.stock_total,
        });
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async deleteRow(row) {
      if (!confirm('Удалить SKU ' + row.sku + '?')) return;
      try {
        await this.api('DELETE', '/api/workspaces/' + this.currentWs + '/skus/' + row.id);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async recalc() {
      try {
        const r = await this.api('POST', '/api/workspaces/' + this.currentWs + '/skus/calc', {});
        this.results = r.results;
      } catch(e) { this.showToast('Ошибка расчёта: ' + e.message); }
    },

    async saveMpAccount() {
      if (!this.mpForm.api_token) { this.showToast('Введи токен'); return; }
      try {
        await this.api('POST', '/api/workspaces/' + this.currentWs + '/marketplace-accounts', {
          marketplace: 'ya_market', ...this.mpForm,
        });
        this.mpForm = {api_token:'', business_id:null, campaign_id:null, label:''};
        this.mpAccounts = await this.api('GET', '/api/workspaces/' + this.currentWs + '/marketplace-accounts');
        this.showToast('Ya.Market API подключён');
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async deleteMpAccount(id) {
      if (!confirm('Удалить аккаунт?')) return;
      try {
        await this.api('DELETE', '/api/workspaces/' + this.currentWs + '/marketplace-accounts/' + id);
        this.mpAccounts = await this.api('GET', '/api/workspaces/' + this.currentWs + '/marketplace-accounts');
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    async importFromYaMarket() {
      if (this.mpAccounts.length === 0) { this.showYaMarket = true; return; }
      this.importing = true;
      try {
        const r = await this.api('POST', '/api/workspaces/' + this.currentWs + '/ya-market/import-offers');
        this.showToast('Импорт: ' + r.created_in_our_db + ' создано, ' + r.updated_in_our_db + ' обновлено');
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
      finally { this.importing = false; }
    },

    async syncPricesFromYaMarket() {
      this.importing = true;
      try {
        const r = await this.api('POST', '/api/workspaces/' + this.currentWs + '/ya-market/sync-prices');
        this.showToast('Цены: ' + r.updated + ' обновлено');
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
      finally { this.importing = false; }
    },

    async syncStocksFromYaMarket() {
      this.syncingStocks = true;
      try {
        const r = await this.api('POST', '/api/workspaces/' + this.currentWs + '/ya-market/sync-stocks');
        this.showToast('Остатки: ' + r.updated + ' обновлено, в наличии ' + r.in_stock + '/' + r.total_skus);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
      finally { this.syncingStocks = false; }
    },

    async onImportCostsFile(evt) {
      const file = evt.target.files[0];
      if (!file) return;
      this.uploadingCosts = true;
      try {
        const fd = new FormData();
        fd.append('file', file);
        const r = await fetch('/api/workspaces/' + this.currentWs + '/skus/import-costs', {
          method: 'POST',
          headers: {'Authorization': 'Bearer ' + this.token},
          body: fd,
        });
        if (!r.ok) throw new Error(await r.text());
        const data = await r.json();
        this.showToast('Обновлено ' + data.updated_cost_rub + '/' + data.matched_by_sku);
        await this.recalc();
      } catch(e) { this.showToast('Ошибка импорта: ' + e.message); }
      finally { this.uploadingCosts = false; evt.target.value = ''; }
    },

    async debugOffer() {
      try {
        const r = await this.api('GET', '/api/workspaces/' + this.currentWs + '/ya-market/debug-offer');
        const off = r.offerMappings && r.offerMappings[0];
        if (!off) { alert('Нет офферов'); return; }
        const pretty = JSON.stringify(off, null, 2);
        const w = window.open('', '_blank');
        w.document.write('<pre style="font:12px monospace;padding:20px;white-space:pre-wrap;word-break:break-all">' + pretty.replace(/</g,'&lt;') + '</pre>');
      } catch(e) { this.showToast('Ошибка: ' + e.message); }
    },

    toggleSort(field) {
      if (this.sortField !== field) { this.sortField = field; this.sortDir = 'asc'; return; }
      if (this.sortDir === 'asc') { this.sortDir = 'desc'; return; }
      this.sortField = null; this.sortDir = 'asc';
    },

    sortArrow(field) {
      if (this.sortField !== field) return '';
      return this.sortDir === 'asc' ? ' \u2191' : ' \u2193';
    },

    get filteredResults() {
      let arr = this.results;
      if (this.onlyWithCost) arr = arr.filter(r => (+r.cost_rub) > 0);
      if (this.onlyInStock)  arr = arr.filter(r => (+r.stock_total) > 0);
      if (this.marginFilter === 'good') arr = arr.filter(r => r.margin_pct >= 15);
      if (this.marginFilter === 'mid')  arr = arr.filter(r => r.margin_pct >= 5 && r.margin_pct < 15);
      if (this.marginFilter === 'bad')  arr = arr.filter(r => r.margin_pct < 5);
      if (this.filter) {
        const q = this.filter.toLowerCase();
        arr = arr.filter(r => (r.sku||'').toLowerCase().includes(q) || (r.name||'').toLowerCase().includes(q));
      }
      if (this.sortField) {
        const f = this.sortField;
        const sign = this.sortDir === 'desc' ? -1 : 1;
        const isNum = ['price_rub','cost_rub','stock_total','profit_rub','margin_pct'].includes(f);
        arr = [...arr].sort((a,b) => {
          let va = a[f], vb = b[f];
          if (isNum) { va = +va || 0; vb = +vb || 0; return sign * (va - vb); }
          va = (va||'').toString().toLowerCase();
          vb = (vb||'').toString().toLowerCase();
          return sign * va.localeCompare(vb, 'ru');
        });
      }
      return arr;
    },

    get summary() {
      let arr = this.results;
      if (this.onlyWithCost) arr = arr.filter(r => (+r.cost_rub) > 0);
      if (this.onlyInStock)  arr = arr.filter(r => (+r.stock_total) > 0);
      if (arr.length === 0) return {total_sku:0, profitable_15plus:0, profitable_5_15:0, losing:0, avg_margin_pct:0};
      const avg = arr.reduce((s,r) => s + (+r.margin_pct||0), 0) / arr.length;
      return {
        total_sku: arr.length,
        profitable_15plus: arr.filter(r => r.margin_pct >= 15).length,
        profitable_5_15:   arr.filter(r => r.margin_pct >= 5 && r.margin_pct < 15).length,
        losing:            arr.filter(r => r.margin_pct < 0).length,
        avg_margin_pct: Math.round(avg * 100) / 100,
      };
    },

    fmtRub(v) { if (v == null || isNaN(v)) return '\u2014'; return Math.round(v).toLocaleString('ru-RU') + ' \u20BD'; },
    fmtPct(v) { if (v == null || isNaN(v)) return '\u2014'; return v.toFixed(1) + '%'; },

    marginBg(pct) {
      if (pct == null || isNaN(pct)) return 'background:rgba(255,255,255,0.06);color:#A1A1AA';
      if (pct >= 15) return 'background:#10B981;color:#053426';
      if (pct >= 5)  return 'background:#FCD34D;color:#3F2A00';
      return 'background:#FB7185;color:#4C0519';
    },

    showToast(text) {
      this.toast.text = text;
      clearTimeout(this._t);
      this._t = setTimeout(() => this.toast.text = '', 4000);
    },
  }
}

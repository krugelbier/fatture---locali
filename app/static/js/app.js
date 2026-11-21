// Fatture Locali & HACCP - Frontend Application Logic
// Krügel – Lavis & Cafè L’Incontro – Pergine
// P.IVA 02562290227

// ==========================================
// 1. STATO GLOBALE DELL'APPLICAZIONE
// ==========================================
let authToken = localStorage.getItem('fl_auth_token') || null;
let currentUser = null;
let activeVenueId = null; // 1 = Krügel – Lavis, 2 = Cafè L’Incontro – Pergine
let activeSection = null; // 'invoices' | 'haccp'

let currentInvoicesTab = 'analytics'; // 'analytics' | 'invoices' | 'unassigned' | 'settings'
let currentHaccpTab = 'labels'; // 'labels' | 'temp' | 'oil' | 'hood' | 'cleaning_walls' | 'cleaning_windows' | 'cleaning_warehouse' | 'pests'

let cachedPermissionsCatalog = [];
let cachedUsers = [];
let cachedProducts = [];
let cachedHaccpProducts = [];
let cachedFridges = [];
let cachedFryers = [];

let cachedLastSavedLotLabels = [];
let cachedHistoryLots = [];
let selectedLotForReprint = null;
let currentHaccpAlerts = [];
let alertsPollingTimer = null;
let pestWizardState = { currentStep: 1, answers: {}, isDirty: false };
let cachedPestInspections = [];

const VOCI_INFESTANTI_ORDINE = [
  "Peli o piume",
  "Segni di roditori",
  "Insetti vivi",
  "Insetti morti",
  "Roditori",
  "Contenitori danneggiati da animali o insetti",
  "Feci o escrementi",
  "Animali infestanti nelle esche"
];

let currentTempEsito = 'CONFORME';
let currentDrilldownContext = null;
let currentDetailInvoiceId = null;
let selectedUnassignedLineIds = new Set();
let filesToUpload = [];

// ==========================================
// 2. UTILITY & FORMATTAZIONE
// ==========================================
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

function formatCurrency(val) {
  if (val === null || val === undefined || isNaN(val)) return '€ 0,00';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(val);
}

function formatQty(val) {
  if (val === null || val === undefined || isNaN(val)) return '0';
  return new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2 }).format(val);
}

function formatForDatetimeLocal(d) {
  const pad = (n) => String(n).padStart(2, '0');
  const year = d.getFullYear();
  const month = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const hours = pad(d.getHours());
  const minutes = pad(d.getMinutes());
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function formatDisplayDateTime(dtStr) {
  if (!dtStr) return '--';
  const d = new Date(dtStr);
  if (isNaN(d.getTime())) return dtStr;
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  const bg = type === 'success' ? 'bg-emerald-600 text-white' : (type === 'error' ? 'bg-rose-600 text-white' : 'bg-slate-800 text-white');
  const icon = type === 'success' ? 'check-circle' : (type === 'error' ? 'alert-octagon' : 'info');

  toast.className = `flex items-center space-x-2 px-4 py-3 rounded-xl shadow-xl text-xs font-semibold ${bg} transition-all duration-300 transform translate-y-2 opacity-0 pointer-events-auto`;
  toast.innerHTML = `<i data-lucide="${icon}" class="w-4 h-4 flex-shrink-0"></i><span>${message}</span>`;
  container.appendChild(toast);
  lucide.createIcons();

  setTimeout(() => {
    toast.classList.remove('translate-y-2', 'opacity-0');
  }, 10);

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 350);
  }, 4000);
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('hidden');
    lucide.createIcons();
  }
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

// ==========================================
// 3. RETE & CLIENT HTTP AUTENTICATO
// ==========================================
async function authFetch(url, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const fetchOptions = {
    ...options,
    headers: headers
  };

  try {
    const res = await fetch(url, fetchOptions);

    if (res.status === 401) {
      // Sessione non valida o scaduta
      authToken = null;
      localStorage.removeItem('fl_auth_token');
      currentUser = null;
      showLoginScreen();
      showToast('Sessione scaduta o non valida. Effettua nuovamente l\'accesso.', 'error');
      throw new Error('Non autorizzato');
    }

    if (res.status === 403) {
      const errData = await res.json().catch(() => ({}));
      showToast(errData.detail || 'Accesso non consentito con i permessi correnti per questo locale.', 'error');
      throw new Error(errData.detail || 'Accesso negato');
    }

    return res;
  } catch (err) {
    if (err.message !== 'Non autorizzato' && err.message !== 'Accesso negato') {
      console.error(`Errore di rete su ${url}:`, err);
    }
    throw err;
  }
}

// Verifica permessi utente
function userHasPermission(permCode, venueId = null) {
  if (!currentUser) return false;
  if (currentUser.is_admin) return true;
  const vid = venueId || activeVenueId;

  if (currentUser.permissions_list && Array.isArray(currentUser.permissions_list)) {
    return currentUser.permissions_list.some(p => (p.permesso === permCode || p.permesso === '*') && p.sede_id === vid);
  }
  if (currentUser.permissions) {
    if (Array.isArray(currentUser.permissions)) {
      return currentUser.permissions.some(p => (p.permesso === permCode || p.permesso === '*') && p.sede_id === vid);
    }
    const map = currentUser.permissions[vid] || [];
    return map.includes(permCode) || map.includes('*');
  }
  return false;
}

function userHasAnyPermission(permCodes, venueId = null) {
  if (!currentUser) return false;
  if (currentUser.is_admin) return true;
  return permCodes.some(code => userHasPermission(code, venueId));
}

// ==========================================
// 4. AUTENTICAZIONE E GESTIONE SCHERMATE
// ==========================================
function hideAllScreens() {
  document.getElementById('screen-login').classList.add('hidden');
  document.getElementById('screen-choose-venue').classList.add('hidden');
  document.getElementById('screen-choose-section').classList.add('hidden');
  document.getElementById('screen-main-app').classList.add('hidden');
}

function showLoginScreen() {
  hideAllScreens();
  document.getElementById('screen-login').classList.remove('hidden');
  document.getElementById('login-username').value = '';
  document.getElementById('login-password').value = '';
  document.getElementById('login-error-msg').classList.add('hidden');
  lucide.createIcons();
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const errBox = document.getElementById('login-error-msg');
  const btn = document.getElementById('btn-login-submit');

  errBox.classList.add('hidden');
  btn.disabled = true;
  btn.textContent = 'Verifica in corso...';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (!res.ok) {
      errBox.textContent = data.detail || 'Credenziali non valide. Riprova.';
      errBox.classList.remove('hidden');
      return;
    }

    authToken = data.session_token;
    localStorage.setItem('fl_auth_token', authToken);
    currentUser = data.user;

    showToast(`Benvenuto, ${currentUser.full_name || currentUser.username}!`);
    navigateToChooseVenue();
  } catch (err) {
    errBox.textContent = 'Errore di connessione al server.';
    errBox.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Accedi';
  }
}

async function handleLogout() {
  if (authToken) {
    try {
      await authFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
      // Ignora errori di rete su logout
    }
  }
  authToken = null;
  localStorage.removeItem('fl_auth_token');
  currentUser = null;
  activeVenueId = null;
  activeSection = null;
  showLoginScreen();
  showToast('Disconnessione effettuata con successo.');
}

// 4.2 Schermata Scegli il Locale
function navigateToChooseVenue() {
  if (!currentUser) {
    showLoginScreen();
    return;
  }

  hideAllScreens();
  document.getElementById('screen-choose-venue').classList.remove('hidden');

  const userBadge = document.getElementById('venue-user-name');
  if (userBadge) {
    userBadge.textContent = `${currentUser.full_name || currentUser.username} ${currentUser.is_admin ? '(Admin)' : ''}`;
  }

  const container = document.getElementById('venue-buttons-container');
  container.innerHTML = '';

  const authSedi = currentUser.authorized_sedi || [];

  if (authSedi.length === 0 && !currentUser.is_admin) {
    container.innerHTML = `
      <div class="col-span-full p-8 bg-white rounded-2xl border border-rose-200 text-center">
        <i data-lucide="shield-alert" class="w-12 h-12 text-rose-500 mx-auto mb-3"></i>
        <h3 class="text-base font-bold text-slate-800">Nessun locale autorizzato</h3>
        <p class="text-xs text-slate-500 mt-1">Il tuo account non ha permessi attivi per alcun locale. Rivolgiti all'amministratore.</p>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  // Definizioni locali
  const venues = [
    {
      id: 1,
      name: 'Krügel – Lavis',
      address: 'Via Nazionale, Lavis (TN) 38015',
      piva: '02562290227',
      icon: 'pizza',
      color: 'amber',
      borderClass: 'border-amber-300 hover:border-amber-500 bg-gradient-to-br from-white to-amber-50/50',
      badgeClass: 'badge-krugel',
      desc: 'Ristorante Pizzeria Krügel • Specialità gastronomiche e birreria'
    },
    {
      id: 2,
      name: 'Cafè L’Incontro – Pergine',
      address: 'Via Tamarisi 2, Pergine Valsugana (TN) 38057',
      piva: '02562290227',
      icon: 'coffee',
      color: 'emerald',
      borderClass: 'border-emerald-300 hover:border-emerald-500 bg-gradient-to-br from-white to-emerald-50/50',
      badgeClass: 'badge-incontro',
      desc: 'Cafè L’Incontro • Caffetteria, bar e ristorazione veloce'
    }
  ];

  venues.forEach(v => {
    const isAuthorized = currentUser.is_admin || authSedi.includes(v.id);
    if (!isAuthorized) return; // Mostra solo i locali autorizzati per quell'account

    const card = document.createElement('div');
    card.className = `p-6 rounded-2xl border-2 ${v.borderClass} shadow-md hover:shadow-xl transition-all cursor-pointer flex flex-col justify-between group`;
    card.onclick = () => selectVenue(v.id);

    card.innerHTML = `
      <div>
        <div class="flex items-center justify-between mb-4">
          <span class="px-2.5 py-1 rounded-md text-xs font-bold ${v.badgeClass}">Sede ${v.id}</span>
          <i data-lucide="arrow-right" class="w-5 h-5 text-slate-400 group-hover:translate-x-1.5 transition-transform"></i>
        </div>
        <h3 class="text-xl font-black text-slate-900 group-hover:text-indigo-900 transition-colors">${v.name}</h3>
        <p class="text-xs text-slate-600 mt-2 font-medium flex items-center space-x-1">
          <i data-lucide="map-pin" class="w-3.5 h-3.5 text-slate-400 flex-shrink-0"></i>
          <span>${v.address}</span>
        </p>
        <p class="text-[11px] text-slate-400 mt-1 font-mono">P.IVA: ${v.piva}</p>
        <p class="text-xs text-slate-500 mt-3 pt-3 border-t border-slate-100">${v.desc}</p>
      </div>
      <div class="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-xs font-bold text-slate-800">
        <span>Seleziona questo locale</span>
        <span class="text-indigo-600">Entra &rarr;</span>
      </div>
    `;
    container.appendChild(card);
  });

  lucide.createIcons();
}

function selectVenue(venueId) {
  activeVenueId = venueId;
  navigateToChooseSection();
}

// 4.3 Schermata Scegli la Sezione
function navigateToChooseSection() {
  if (!currentUser || !activeVenueId) {
    navigateToChooseVenue();
    return;
  }

  hideAllScreens();
  document.getElementById('screen-choose-section').classList.remove('hidden');

  // Aggiorna badge locale attivo
  const venueBadge = document.getElementById('section-venue-badge');
  const venueName = activeVenueId === 1 ? 'Krügel – Lavis' : 'Cafè L’Incontro – Pergine';
  if (venueBadge) {
    venueBadge.textContent = venueName;
    venueBadge.className = activeVenueId === 1 ? 'px-2.5 py-1 rounded-md text-sm font-bold badge-krugel' : 'px-2.5 py-1 rounded-md text-sm font-bold badge-incontro';
  }

  // Mostra pulsante cambia locale se ha accesso a entrambi
  const btnChangeVenue = document.getElementById('btn-change-venue-from-section');
  if (btnChangeVenue) {
    const hasMultipleVenues = currentUser.is_admin || (currentUser.authorized_sedi && currentUser.authorized_sedi.length > 1);
    if (hasMultipleVenues) btnChangeVenue.classList.remove('hidden');
    else btnChangeVenue.classList.add('hidden');
  }

  // Verifica permessi per mostrare le due schede (Fatture e prezzi vs HACCP)
  const cardInvoices = document.getElementById('card-section-invoices');
  const cardHaccp = document.getElementById('card-section-haccp');

  const hasInvoices = currentUser.is_admin || userHasAnyPermission([
    'fatture.view', 'fatture.import', 'fatture.assign', 'fatture.products'
  ], activeVenueId);

  const hasHaccp = currentUser.is_admin || userHasAnyPermission([
    'haccp.labels.view', 'haccp.labels.create', 'haccp.labels.print',
    'haccp.temp.view', 'haccp.temp.record', 'haccp.temp.manage',
    'haccp.oil.view', 'haccp.oil.record', 'haccp.oil.manage',
    'haccp.hood.view', 'haccp.hood.record',
    'haccp.cleaning.walls.view', 'haccp.cleaning.walls.record',
    'haccp.cleaning.windows.view', 'haccp.cleaning.windows.record',
    'haccp.cleaning.warehouse.view', 'haccp.cleaning.warehouse.record',
    'haccp.pests.view', 'haccp.pests.record'
  ], activeVenueId);

  if (cardInvoices) {
    if (hasInvoices) cardInvoices.classList.remove('hidden');
    else cardInvoices.classList.add('hidden');
  }

  if (cardHaccp) {
    if (hasHaccp) cardHaccp.classList.remove('hidden');
    else cardHaccp.classList.add('hidden');
  }

  lucide.createIcons();
}

function enterSection(sectionName) {
  activeSection = sectionName;
  hideAllScreens();
  document.getElementById('screen-main-app').classList.remove('hidden');

  // Aggiorna intestazione
  const venueName = activeVenueId === 1 ? 'Krügel – Lavis' : 'Cafè L’Incontro – Pergine';
  document.getElementById('active-venue-name-header').textContent = venueName;

  const sectionLabel = sectionName === 'invoices' ? 'Sezione: Fatture e prezzi' : 'Sezione: Autocontrollo HACCP';
  const sectionLabelEl = document.getElementById('active-section-name-header');
  sectionLabelEl.textContent = sectionLabel;
  sectionLabelEl.className = sectionName === 'invoices' ? 'text-xs font-semibold text-indigo-600' : 'text-xs font-semibold text-emerald-600';

  // Pulsante Cambia Locale visibile per chi accede a entrambi
  const btnChangeVenue = document.getElementById('btn-change-venue-header');
  const hasMultipleVenues = currentUser.is_admin || (currentUser.authorized_sedi && currentUser.authorized_sedi.length > 1);
  if (hasMultipleVenues) btnChangeVenue.classList.remove('hidden');
  else btnChangeVenue.classList.add('hidden');

  // Pulsante Gestione Utenti riservato all'amministratore
  const btnManageUsers = document.getElementById('btn-manage-users-header');
  if (currentUser.is_admin) btnManageUsers.classList.remove('hidden');
  else btnManageUsers.classList.add('hidden');

  if (sectionName === 'invoices') {
    document.getElementById('nav-tabs-invoices').classList.remove('hidden');
    document.getElementById('nav-tabs-haccp').classList.add('hidden');
    document.getElementById('section-invoices-content').classList.remove('hidden');
    document.getElementById('section-haccp-content').classList.add('hidden');

    document.getElementById('invoices-venue-label').textContent = venueName;

    // Controlla permessi per bottoni fatture
    const btnUpload = document.getElementById('btn-open-upload-modal');
    if (userHasPermission('fatture.import')) btnUpload.classList.remove('hidden');
    else btnUpload.classList.add('hidden');

    const btnDemo = document.getElementById('btn-load-demo');
    if (currentUser.is_admin) btnDemo.classList.remove('hidden');
    else btnDemo.classList.add('hidden');

    switchInvoicesTab('analytics');
  } else {
    document.getElementById('nav-tabs-invoices').classList.add('hidden');
    document.getElementById('nav-tabs-haccp').classList.remove('hidden');
    document.getElementById('section-invoices-content').classList.add('hidden');
    document.getElementById('section-haccp-content').classList.remove('hidden');

    // Filtra schede HACCP visibili in base ai permessi
    const canLabels = userHasAnyPermission(['haccp.labels.view', 'haccp.labels.create', 'haccp.labels.print']);
    const canTemp = userHasAnyPermission(['haccp.temp.view', 'haccp.temp.record', 'haccp.temp.manage']);
    const canOil = userHasAnyPermission(['haccp.oil.view', 'haccp.oil.record', 'haccp.oil.manage']);
    const canHood = userHasAnyPermission(['haccp.hood.view', 'haccp.hood.record']);
    const canWalls = userHasAnyPermission(['haccp.cleaning.walls.view', 'haccp.cleaning.walls.record']);
    const canWindows = userHasAnyPermission(['haccp.cleaning.windows.view', 'haccp.cleaning.windows.record']);
    const canWarehouse = userHasAnyPermission(['haccp.cleaning.warehouse.view', 'haccp.cleaning.warehouse.record']);
    const canPests = userHasAnyPermission(['haccp.pests.view', 'haccp.pests.record']);

    const btnLabels = document.getElementById('tab-btn-haccp-labels');
    const btnTemp = document.getElementById('tab-btn-haccp-temp');
    const btnOil = document.getElementById('tab-btn-haccp-oil');
    const btnHood = document.getElementById('tab-btn-haccp-hood');
    const btnWalls = document.getElementById('tab-btn-haccp-cleaning_walls');
    const btnWindows = document.getElementById('tab-btn-haccp-cleaning_windows');
    const btnWarehouse = document.getElementById('tab-btn-haccp-cleaning_warehouse');
    const btnPests = document.getElementById('tab-btn-haccp-pests');

    if (btnLabels) { if (canLabels) btnLabels.classList.remove('hidden'); else btnLabels.classList.add('hidden'); }
    if (btnTemp) { if (canTemp) btnTemp.classList.remove('hidden'); else btnTemp.classList.add('hidden'); }
    if (btnOil) { if (canOil) btnOil.classList.remove('hidden'); else btnOil.classList.add('hidden'); }
    if (btnHood) { if (canHood) btnHood.classList.remove('hidden'); else btnHood.classList.add('hidden'); }
    if (btnWalls) { if (canWalls) btnWalls.classList.remove('hidden'); else btnWalls.classList.add('hidden'); }
    if (btnWindows) { if (canWindows) btnWindows.classList.remove('hidden'); else btnWindows.classList.add('hidden'); }
    if (btnWarehouse) { if (canWarehouse) btnWarehouse.classList.remove('hidden'); else btnWarehouse.classList.add('hidden'); }
    if (btnPests) { if (canPests) btnPests.classList.remove('hidden'); else btnPests.classList.add('hidden'); }

    // Carica avvisi scaduti HACCP per il locale e avvia polling periodico
    loadHaccpAlerts();
    if (alertsPollingTimer) clearInterval(alertsPollingTimer);
    alertsPollingTimer = setInterval(loadHaccpAlerts, 30000);

    // Seleziona la prima scheda consentita
    if (canLabels) switchHaccpTab('labels');
    else if (canTemp) switchHaccpTab('temp');
    else if (canOil) switchHaccpTab('oil');
    else if (canHood) switchHaccpTab('hood');
    else if (canWalls) switchHaccpTab('cleaning_walls');
    else if (canWindows) switchHaccpTab('cleaning_windows');
    else if (canWarehouse) switchHaccpTab('cleaning_warehouse');
    else if (canPests) switchHaccpTab('pests');
  }

  lucide.createIcons();
}

// Switcher Tab Sezione Fatture
function switchInvoicesTab(tab) {
  currentInvoicesTab = tab;
  if (alertsPollingTimer) { clearInterval(alertsPollingTimer); alertsPollingTimer = null; }
  ['analytics', 'invoices', 'unassigned', 'settings'].forEach(t => {
    const view = document.getElementById(`invoices-subview-${t}`);
    const btn = document.getElementById(`tab-btn-${t}`);
    if (view && btn) {
      if (t === tab) {
        view.classList.remove('hidden');
        btn.className = 'tab-link py-3 px-1 border-b-2 font-semibold text-sm flex items-center space-x-2 border-indigo-600 text-indigo-600';
      } else {
        view.classList.add('hidden');
        btn.className = 'tab-link py-3 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 border-transparent text-slate-500 hover:text-slate-800';
      }
    }
  });

  if (tab === 'analytics') loadAnalytics();
  else if (tab === 'invoices') loadInvoices();
  else if (tab === 'unassigned') loadUnassigned();
  else if (tab === 'settings') loadSettings();

  lucide.createIcons();
}

// Switcher Tab Sezione HACCP
function switchHaccpTab(tab) {
  currentHaccpTab = tab;
  const allHaccpTabs = ['labels', 'temp', 'oil', 'hood', 'cleaning_walls', 'cleaning_windows', 'cleaning_warehouse', 'pests'];
  allHaccpTabs.forEach(t => {
    const view = document.getElementById(`haccp-subview-${t}`);
    const btn = document.getElementById(`tab-btn-haccp-${t}`);
    if (view && btn) {
      if (t === tab) {
        view.classList.remove('hidden');
        btn.className = 'haccp-tab-link py-3 px-2 sm:px-3 border-b-2 font-bold text-sm flex items-center space-x-2 border-emerald-600 text-emerald-700 flex-shrink-0';
      } else {
        view.classList.add('hidden');
        btn.className = 'haccp-tab-link py-3 px-2 sm:px-3 border-b-2 font-semibold text-sm flex items-center space-x-2 border-transparent text-slate-500 hover:text-slate-800 flex-shrink-0';
      }
    }
  });

  if (tab === 'labels') loadHaccpLabels();
  else if (tab === 'temp') loadHaccpTemperature();
  else if (tab === 'oil') loadHaccpOil();
  else if (tab === 'hood') loadHaccpHood();
  else if (tab === 'cleaning_walls') loadHaccpCleaning('muri');
  else if (tab === 'cleaning_windows') loadHaccpCleaning('vetri');
  else if (tab === 'cleaning_warehouse') loadHaccpCleaning('magazzino');
  else if (tab === 'pests') loadHaccpPests();

  // Ricarica e aggiorna gli avvisi specifici per questa scheda
  renderTabSpecificAlerts();

  lucide.createIcons();
}

// ==========================================
// 5. HACCP: ETICHETTE ALIMENTI & LOTTI (CONFORME HACCP)
// ==========================================
function adjustPiecesInput(delta) {
  const el = document.getElementById('label-numero-pezzi');
  if (!el) return;
  let val = parseInt(el.value) || 1;
  val = Math.max(1, val + delta);
  el.value = val;
  updateLabelPreviewFromForm();
}

async function loadHaccpLabels() {
  try {
    // 1. Carica lista prodotti con durate
    const pRes = await authFetch(`/api/haccp/labels/products?sede_id=${activeVenueId}`);
    const pData = await pRes.json();
    cachedHaccpProducts = pData.products || [];

    const selectEl = document.getElementById('label-select-product');
    selectEl.innerHTML = '<option value="">-- Seleziona dal piano HACCP --</option>';
    cachedHaccpProducts.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.nome_prodotto} (${p.durata_ore} ore)`;
      opt.dataset.duration = p.durata_ore;
      opt.dataset.name = p.nome_prodotto;
      selectEl.appendChild(opt);
    });

    // 2. Proponi data e ora correnti
    const now = new Date();
    const dtPrepEl = document.getElementById('label-dt-prep');
    dtPrepEl.value = formatForDatetimeLocal(now);

    // Operatore predefinito dall'account
    const opEl = document.getElementById('label-preparato-da');
    if (!opEl.value && currentUser) {
      opEl.value = currentUser.full_name || currentUser.username;
    }

    // Prefisso lotto interno previsto
    const lottoPrevEl = document.getElementById('label-lotto-interno-preview');
    if (lottoPrevEl) {
      const pref = activeVenueId === 1 ? 'LAV-XXXXXX' : 'PER-XXXXXX';
      lottoPrevEl.textContent = `${pref} (generato al salvataggio)`;
    }

    // Seleziona il primo prodotto se disponibile
    if (cachedHaccpProducts.length > 0 && !selectEl.value) {
      selectEl.value = cachedHaccpProducts[0].id;
      handleLabelProductSelect(selectEl);
    } else {
      recalculateLabelExpiry();
    }

    // 3. Carica storico etichette e lotti
    loadHaccpLabelsHistory();
  } catch (err) {
    console.error('Errore caricamento etichette HACCP:', err);
  }
}

function handleLabelProductSelect(selectEl) {
  const customInput = document.getElementById('label-custom-product');
  const durationHoursEl = document.getElementById('label-duration-hours');

  if (selectEl.value) {
    customInput.value = '';
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    const duration = parseInt(selectedOpt.dataset.duration) || 48;
    durationHoursEl.textContent = duration;
  } else {
    durationHoursEl.textContent = '48';
  }

  recalculateLabelExpiry();
}

function recalculateLabelExpiry() {
  const dtPrepVal = document.getElementById('label-dt-prep').value;
  if (!dtPrepVal) return;

  const durationHours = parseInt(document.getElementById('label-duration-hours').textContent) || 48;
  const prepDate = new Date(dtPrepVal);
  if (isNaN(prepDate.getTime())) return;

  // Calcolo esatto aggiungendo ore effettive (timedelta(hours=48))
  const expDate = new Date(prepDate.getTime() + durationHours * 3600 * 1000);
  document.getElementById('label-dt-exp').value = formatForDatetimeLocal(expDate);

  updateLabelPreviewFromForm();
}

function updateLabelPreviewDimensions() {
  const wMm = parseInt(document.getElementById('label-width-mm').value) || 60;
  const hMm = parseInt(document.getElementById('label-height-mm').value) || 40;

  // Scala grafica a schermo
  const previewBox = document.getElementById('label-preview-box');
  if (previewBox) {
    previewBox.style.width = `${Math.max(220, Math.min(380, wMm * 4.4))}px`;
    previewBox.style.minHeight = `${Math.max(160, Math.min(280, hMm * 4.4))}px`;
  }
}

function updateLabelPreviewFromForm() {
  const prepVal = document.getElementById('label-dt-prep').value;
  const expVal = document.getElementById('label-dt-exp').value;
  const opVal = document.getElementById('label-preparato-da').value.trim() || 'Nome Operatore';
  const lottoOrig = document.getElementById('label-lotto-originale').value.trim() || 'LOT-ORIG-01';
  const numPezzi = Math.max(1, parseInt(document.getElementById('label-numero-pezzi').value) || 1);

  const selectEl = document.getElementById('label-select-product');
  const customVal = document.getElementById('label-custom-product').value.trim();
  let prodName = customVal;
  if (!prodName && selectEl.value) {
    prodName = selectEl.options[selectEl.selectedIndex].dataset.name;
  }
  if (!prodName) prodName = 'Prodotto Alimentare';

  const venueName = activeVenueId === 1 ? 'Krügel – Lavis' : 'Cafè L’Incontro – Pergine';
  const pref = activeVenueId === 1 ? 'LAV-000001' : 'PER-000001';

  const prevVenue = document.getElementById('prev-venue-name');
  if (prevVenue) prevVenue.textContent = venueName;
  const prevProd = document.getElementById('prev-prodotto');
  if (prevProd) prevProd.textContent = prodName;
  const prevOp = document.getElementById('prev-operatore');
  if (prevOp) prevOp.textContent = opVal;
  const prevPezzo = document.getElementById('prev-pezzo-num');
  if (prevPezzo) prevPezzo.textContent = `Pezzo 1 di ${numPezzi}`;
  const prevLottoOrig = document.getElementById('prev-lotto-originale');
  if (prevLottoOrig) prevLottoOrig.textContent = lottoOrig;
  const prevLottoInt = document.getElementById('prev-lotto-interno');
  if (prevLottoInt && (!prevLottoInt.dataset.saved || prevLottoInt.dataset.saved !== 'true')) {
    prevLottoInt.textContent = pref;
  }
  const prevPrep = document.getElementById('prev-dt-prep');
  if (prevPrep) prevPrep.textContent = formatDisplayDateTime(prepVal);
  const prevExp = document.getElementById('prev-dt-exp');
  if (prevExp) prevExp.textContent = formatDisplayDateTime(expVal);

  const btnSaveText = document.getElementById('btn-save-print-label-text');
  if (btnSaveText) {
    btnSaveText.textContent = numPezzi > 1 ? `Salva e Stampa tutte le ${numPezzi} Etichette` : 'Salva e Stampa Etichetta';
  }

  updateLabelPreviewDimensions();
}

async function handleCreateLabelSubmit(event) {
  event.preventDefault();
  if (!userHasPermission('haccp.labels.create')) {
    showToast('Non hai il permesso di registrare nuove etichette.', 'error');
    return;
  }

  const selectEl = document.getElementById('label-select-product');
  const customVal = document.getElementById('label-custom-product').value.trim();
  let prodName = customVal;
  let prodId = null;
  if (!prodName && selectEl.value) {
    prodId = parseInt(selectEl.value);
    prodName = selectEl.options[selectEl.selectedIndex].dataset.name;
  }

  if (!prodName) {
    showToast('Seleziona o specifica il nome del prodotto alimentare.', 'error');
    return;
  }

  const lottoOrig = document.getElementById('label-lotto-originale').value.trim();
  if (!lottoOrig) {
    showToast('Il campo Lotto originale è obbligatorio.', 'error');
    document.getElementById('label-lotto-originale').focus();
    return;
  }

  const numPezzi = Math.max(1, parseInt(document.getElementById('label-numero-pezzi').value) || 1);
  const preparatoDa = document.getElementById('label-preparato-da').value.trim();
  const dtPrep = document.getElementById('label-dt-prep').value;
  const dtExp = document.getElementById('label-dt-exp').value;
  const durationHours = parseInt(document.getElementById('label-duration-hours').textContent) || 48;
  const widthMm = parseInt(document.getElementById('label-width-mm').value) || 60;
  const heightMm = parseInt(document.getElementById('label-height-mm').value) || 40;

  // Chiave di idempotenza per prevenire doppi tocchi accidentali
  const idempotencyKey = `lot_${activeVenueId}_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

  const submitBtn = document.getElementById('btn-print-label');
  if (submitBtn) submitBtn.disabled = true;

  const payload = {
    sede_id: activeVenueId,
    prodotto_id: prodId,
    prodotto_nome: prodName,
    preparato_da: preparatoDa,
    lotto_originale: lottoOrig,
    numero_pezzi: numPezzi,
    data_preparazione: dtPrep,
    data_scadenza: dtExp,
    durata_ore: durationHours,
    formato_larghezza_mm: widthMm,
    formato_altezza_mm: heightMm,
    idempotency_key: idempotencyKey
  };

  try {
    const res = await authFetch('/api/haccp/labels/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Errore durante la creazione del lotto.');
    }

    const data = await res.json();
    showToast(`Lotto ${data.lotto_interno} creato con successo (${data.numero_pezzi} etichette)!`);

    // Aggiorna stato e anteprima
    cachedLastSavedLotLabels = data.labels || [];
    const prevLottoInt = document.getElementById('prev-lotto-interno');
    if (prevLottoInt) {
      prevLottoInt.textContent = data.lotto_interno;
      prevLottoInt.dataset.saved = 'true';
    }

    const resBox = document.getElementById('label-save-result-box');
    const resLotto = document.getElementById('res-lotto-interno');
    const resCount = document.getElementById('res-lotto-count');
    const resBtnText = document.getElementById('btn-print-all-saved-text');
    if (resBox && resLotto && resCount && resBtnText) {
      resLotto.textContent = data.lotto_interno;
      resCount.textContent = `${data.numero_pezzi} ${data.numero_pezzi === 1 ? 'etichetta creata' : 'etichette create'}`;
      resBtnText.textContent = `Stampa tutte le ${data.numero_pezzi} etichette`;
      resBox.classList.remove('hidden');
    }

    // Invia alla stampa un'etichetta per ciascun pezzo generato
    if (userHasPermission('haccp.labels.print')) {
      printLabelsBatch(cachedLastSavedLotLabels);
    }

    loadHaccpLabelsHistory();
  } catch (err) {
    console.error('Errore creazione etichetta:', err);
    showToast(err.message || 'Errore durante il salvataggio del lotto.', 'error');
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function printAllLabelsFromLastBatch() {
  if (!cachedLastSavedLotLabels || cachedLastSavedLotLabels.length === 0) {
    showToast('Nessun lotto salvato di recente da stampare.', 'error');
    return;
  }
  printLabelsBatch(cachedLastSavedLotLabels);
}

function printLabelsBatch(labels) {
  if (!labels || labels.length === 0) return;
  const wrapper = document.getElementById('printable-label-wrapper');
  if (!wrapper) return;

  const venueName = activeVenueId === 1 ? 'Krügel – Lavis' : 'Cafè L’Incontro – Pergine';
  wrapper.innerHTML = '';

  labels.forEach(lbl => {
    const wMm = lbl.formato_larghezza_mm || lbl.larghezza_mm || 60;
    const hMm = lbl.formato_altezza_mm || lbl.altezza_mm || 40;
    const pezzoTxt = lbl.pezzo_label || `Pezzo ${lbl.numero_pezzo || 1} di ${lbl.numero_pezzi || 1}`;

    const div = document.createElement('div');
    div.className = 'haccp-printable-single-label';
    div.style.width = `${wMm}mm`;
    div.style.minHeight = `${hMm}mm`;
    div.style.border = '2px solid #000';
    div.style.padding = '2.5mm 3.5mm';
    div.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
    div.style.boxSizing = 'border-box';
    div.style.display = 'flex';
    div.style.flexDirection = 'column';
    div.style.justifyContent = 'space-between';
    div.style.background = '#fff';
    div.style.color = '#000';

    div.innerHTML = `
      <div>
        <div style="font-size: 7.5pt; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid #000; padding-bottom: 0.8mm; display: flex; justify-content: space-between; align-items: center;">
          <span>${escapeHtml(venueName)}</span>
          <span style="font-family: monospace; font-size: 8pt; font-weight: 900;">${escapeHtml(lbl.lotto_interno || '')}</span>
        </div>
        <div style="font-size: 11pt; font-weight: 900; line-height: 1.15; margin-top: 1.5mm; text-transform: uppercase; word-break: break-word;">
          ${escapeHtml(lbl.prodotto_nome || lbl.prodotto)}
        </div>
        <div style="font-size: 7.5pt; margin-top: 1mm; display: flex; justify-content: space-between; align-items: center;">
          <span>PREP. DA: <strong>${escapeHtml(lbl.preparato_da)}</strong></span>
          <strong style="font-size: 8pt; background: #eee; padding: 0.5mm 1.5mm; border-radius: 2px;">${escapeHtml(pezzoTxt)}</strong>
        </div>
        ${lbl.lotto_originale ? `
        <div style="font-size: 7pt; margin-top: 0.8mm; color: #222;">
          LOTTO ORIG.: <span style="font-family: monospace; font-weight: bold;">${escapeHtml(lbl.lotto_originale)}</span>
        </div>` : ''}
      </div>
      <div style="border-top: 1px dashed #000; padding-top: 1mm; font-size: 7.5pt; margin-top: 1.5mm;">
        <div style="display: flex; justify-content: space-between;">
          <span>PREPARAZIONE:</span>
          <strong style="font-family: monospace;">${formatDisplayDateTime(lbl.data_preparazione)}</strong>
        </div>
        <div style="display: flex; justify-content: space-between; margin-top: 0.8mm; font-size: 8.5pt;">
          <span style="font-weight: bold;">SCADENZA:</span>
          <strong style="font-family: monospace; font-weight: 900;">${formatDisplayDateTime(lbl.data_scadenza)}</strong>
        </div>
      </div>
    `;
    wrapper.appendChild(div);
  });

  // Mostra wrapper per il print engine e invoca window.print()
  wrapper.classList.remove('hidden');
  window.print();
  setTimeout(() => {
    wrapper.classList.add('hidden');
  }, 1000);
}

function executeTestPrint() {
  const venueName = activeVenueId === 1 ? 'Krügel – Lavis' : 'Cafè L’Incontro – Pergine';
  const now = new Date();
  const exp = new Date(now.getTime() + 48 * 3600 * 1000);
  const wMm = parseInt(document.getElementById('label-width-mm').value) || 60;
  const hMm = parseInt(document.getElementById('label-height-mm').value) || 40;

  printLabelsBatch([{
    venue_name: venueName,
    prodotto_nome: 'PRODOTTO PROVA HACCP',
    preparato_da: currentUser ? currentUser.full_name : 'Operatore Test',
    lotto_originale: 'TEST-ORIG-001',
    lotto_interno: activeVenueId === 1 ? 'LAV-PROVA' : 'PER-PROVA',
    numero_pezzo: 1,
    numero_pezzi: 1,
    pezzo_label: 'Pezzo 1 di 1 (Stampa Prova)',
    data_preparazione: now.toISOString(),
    data_scadenza: exp.toISOString(),
    formato_larghezza_mm: wMm,
    formato_altezza_mm: hMm
  }]);
}

async function loadHaccpLabelsHistory() {
  try {
    const sInput = document.getElementById('labels-search-input');
    const dFromInput = document.getElementById('labels-date-from');
    const dToInput = document.getElementById('labels-date-to');

    let url = `/api/haccp/labels/history?sede_id=${activeVenueId}`;
    if (sInput && sInput.value.trim()) url += `&search=${encodeURIComponent(sInput.value.trim())}`;
    if (dFromInput && dFromInput.value) url += `&data_from=${encodeURIComponent(dFromInput.value)}`;
    if (dToInput && dToInput.value) url += `&data_to=${encodeURIComponent(dToInput.value)}`;

    const res = await authFetch(url);
    const data = await res.json();
    cachedHistoryLots = data.lotti || data.labels || [];

    const tbody = document.getElementById('labels-history-table-body');
    tbody.innerHTML = '';

    const countEl = document.getElementById('labels-history-count');
    if (countEl) countEl.textContent = `${data.count || cachedHistoryLots.length} lotti registrati`;

    if (!cachedHistoryLots || cachedHistoryLots.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-slate-400">Nessun lotto o etichetta trovata per questo locale.</td></tr>`;
      return;
    }

    cachedHistoryLots.forEach(lot => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition-colors';
      const lotId = lot.lotto_id || lot.id;
      const isLegacy = !lot.lotto_id;
      const numPezzi = lot.numero_pezzi || 1;

      tr.innerHTML = `
        <td class="py-2.5 px-4 font-mono font-bold text-slate-900">
          <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">${escapeHtml(lot.lotto_interno || 'PRE-AGGIORNAMENTO')}</span>
        </td>
        <td class="py-2.5 px-4 font-mono text-slate-700">${escapeHtml(lot.lotto_originale || '--')}</td>
        <td class="py-2.5 px-4 font-bold text-slate-900">${escapeHtml(lot.prodotto_nome || lot.prodotto)}</td>
        <td class="py-2.5 px-4 font-medium text-slate-700">${escapeHtml(lot.preparato_da)}</td>
        <td class="py-2.5 px-4 text-slate-600">
          <div>Prep: <span class="font-mono">${formatDisplayDateTime(lot.data_preparazione)}</span></div>
          <div class="font-bold text-emerald-900">Scad: <span class="font-mono">${formatDisplayDateTime(lot.data_scadenza)}</span></div>
        </td>
        <td class="py-2.5 px-4 text-center font-bold text-slate-700">
          <span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">
            ${numPezzi} ${numPezzi === 1 ? 'pezzo' : 'pezzi'}
          </span>
        </td>
        <td class="py-2.5 px-4 text-right">
          <div class="flex items-center justify-end space-x-1.5">
            ${isLegacy ? `
              <button onclick="reprintSinglePiece(${lot.id})" class="px-2.5 py-1 rounded-lg text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 flex items-center space-x-1">
                <i data-lucide="printer" class="w-3.5 h-3.5 text-emerald-600"></i>
                <span>Ristampa</span>
              </button>
            ` : `
              <button onclick="reprintEntireLot(${lotId})" class="px-2.5 py-1 rounded-lg text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 shadow-xs flex items-center space-x-1" title="Stampa tutte le etichette del lotto">
                <i data-lucide="printer" class="w-3.5 h-3.5"></i>
                <span>Stampa lotto (${numPezzi})</span>
              </button>
              <button onclick="openReprintPiecesModal(${lotId})" class="px-2 py-1 rounded-lg text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 flex items-center space-x-1" title="Seleziona e ristampa singolo pezzo">
                <i data-lucide="layers" class="w-3.5 h-3.5 text-slate-500"></i>
                <span>Pezzi...</span>
              </button>
            `}
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });

    lucide.createIcons();
  } catch (err) {
    console.error('Errore storico etichette:', err);
  }
}

function resetLabelSearchFilters() {
  const s = document.getElementById('labels-search-input');
  const f = document.getElementById('labels-date-from');
  const t = document.getElementById('labels-date-to');
  if (s) s.value = '';
  if (f) f.value = '';
  if (t) t.value = '';
  loadHaccpLabelsHistory();
}

function openReprintPiecesModal(lotId) {
  const lot = cachedHistoryLots.find(l => (l.lotto_id || l.id) === lotId);
  if (!lot) return;

  selectedLotForReprint = lot;
  document.getElementById('reprint-modal-lot-label').textContent = `Lotto: ${lot.lotto_interno} (${lot.lotto_originale ? `Orig: ${lot.lotto_originale}` : ''})`;
  document.getElementById('reprint-modal-prod-name').textContent = lot.prodotto_nome || lot.prodotto;
  document.getElementById('reprint-modal-meta').textContent = `Prep: ${formatDisplayDateTime(lot.data_preparazione)} • Scad: ${formatDisplayDateTime(lot.data_scadenza)} • Operatore: ${lot.preparato_da}`;
  document.getElementById('reprint-modal-all-btn-text').textContent = `Stampa tutte le ${lot.numero_pezzi || 1} etichette`;

  const listContainer = document.getElementById('reprint-modal-pieces-list');
  listContainer.innerHTML = '';

  const pezzi = lot.pezzi || [];
  if (pezzi.length === 0) {
    listContainer.innerHTML = `<div class="p-3 text-center text-slate-400">Nessun singolo pezzo registrato. Usa la ristampa lotto.</div>`;
  } else {
    pezzi.forEach(p => {
      const item = document.createElement('div');
      item.className = 'p-2.5 bg-white border border-slate-200 rounded-lg flex items-center justify-between text-xs hover:border-emerald-300 transition-colors';
      item.innerHTML = `
        <div class="flex items-center space-x-2">
          <span class="font-bold text-slate-900 bg-slate-100 px-2 py-0.5 rounded font-mono text-[11px]">${p.pezzo_label || `Pezzo ${p.numero_pezzo} di ${p.numero_pezzi}`}</span>
          <span class="text-slate-500 font-mono text-[11px]">${lot.lotto_interno}</span>
        </div>
        <button onclick="reprintSinglePiece(${p.id})" class="px-3 py-1 rounded-md text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-300 flex items-center space-x-1">
          <i data-lucide="printer" class="w-3.5 h-3.5 text-emerald-600"></i>
          <span>Ristampa Pezzo ${p.numero_pezzo}</span>
        </button>
      `;
      listContainer.appendChild(item);
    });
  }

  openModal('modal-reprint-pieces');
  lucide.createIcons();
}

function executeReprintEntireLotFromModal() {
  if (selectedLotForReprint) {
    reprintEntireLot(selectedLotForReprint.lotto_id || selectedLotForReprint.id);
    closeModal('modal-reprint-pieces');
  }
}

async function reprintEntireLot(lotId) {
  if (!userHasPermission('haccp.labels.print')) {
    showToast('Non hai il permesso di stampare etichette.', 'error');
    return;
  }
  try {
    const res = await authFetch(`/api/haccp/labels/lots/${lotId}/reprint`);
    if (!res.ok) throw new Error('Errore durante il recupero del lotto.');
    const data = await res.json();
    printLabelsBatch(data.labels);
    showToast(`Ristampa intero lotto ${data.lotto_interno} (${data.numero_pezzi} pezzi)`);
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Errore ristampa lotto', 'error');
  }
}

async function reprintSinglePiece(labelId) {
  if (!userHasPermission('haccp.labels.print')) {
    showToast('Non hai il permesso di stampare etichette.', 'error');
    return;
  }
  try {
    const res = await authFetch(`/api/haccp/labels/${labelId}/reprint`);
    if (!res.ok) throw new Error('Errore durante il recupero dell\'etichetta.');
    const data = await res.json();
    const lbl = data.label;
    printLabelsBatch([lbl]);
    showToast(`Ristampato ${lbl.pezzo_label || `Pezzo ${lbl.numero_pezzo || 1}`} con dati originali`);
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Errore ristampa etichetta', 'error');
  }
}

function openNewHaccpProductModal() {
  document.getElementById('hprod-name').value = '';
  document.getElementById('hprod-hours').value = '48';
  document.getElementById('hprod-cat').value = '';
  openModal('modal-haccp-product');
}

async function handleSaveHaccpProductSubmit(event) {
  event.preventDefault();
  const payload = {
    sede_id: activeVenueId,
    nome_prodotto: document.getElementById('hprod-name').value.trim(),
    durata_ore: parseInt(document.getElementById('hprod-hours').value) || 48,
    categoria: document.getElementById('hprod-cat').value.trim() || null
  };

  try {
    const res = await authFetch('/api/haccp/labels/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    closeModal('modal-haccp-product');
    showToast(data.message);
    loadHaccpLabels();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// 6. HACCP: TEMPERATURE FRIGORIFERI
// ==========================================
async function loadHaccpTemperature() {
  try {
    // 1. Carica lista frighi per questo locale
    const res = await authFetch(`/api/haccp/temperature/fridges?sede_id=${activeVenueId}`);
    const data = await res.json();
    cachedFridges = data.fridges || [];

    // Mostra bottone gestisci frighi se ha permesso
    const btnAdd = document.getElementById('btn-add-fridge');
    if (userHasPermission('haccp.temp.manage')) btnAdd.classList.remove('hidden');
    else btnAdd.classList.add('hidden');

    // Popola cards frighi
    const container = document.getElementById('fridges-cards-container');
    container.innerHTML = '';

    const selFridge = document.getElementById('temp-select-fridge');
    selFridge.innerHTML = '<option value="">-- Seleziona Frigorifero / Cella --</option>';

    const selFilter = document.getElementById('temp-history-fridge-filter');
    selFilter.innerHTML = '<option value="">Tutti i frigoriferi</option>';

    cachedFridges.forEach(f => {
      // Option per select
      const opt = document.createElement('option');
      opt.value = f.id;
      opt.textContent = `${f.nome_frigorifero} (${f.temperatura_minima}°C / ${f.temperatura_massima}°C)`;
      opt.dataset.tmin = f.temperatura_minima;
      opt.dataset.tmax = f.temperatura_massima;
      selFridge.appendChild(opt);

      const optF = document.createElement('option');
      optF.value = f.id;
      optF.textContent = f.nome_frigorifero;
      selFilter.appendChild(optF);

      // Card grafica frigorifero
      const card = document.createElement('div');
      const isOk = f.ultimo_esito === 'CONFORME';
      const hasRec = f.ultima_temperatura !== null && f.ultima_temperatura !== undefined;
      let statusBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-500">Nessuna lettura</span>`;
      let borderCol = 'border-slate-200';

      if (hasRec) {
        if (isOk) {
          statusBadge = `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">C – Conforme</span>`;
          borderCol = 'border-emerald-300 bg-emerald-50/20';
        } else {
          statusBadge = `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">NC – Non conforme</span>`;
          borderCol = 'border-rose-300 bg-rose-50/30';
        }
      }

      card.className = `p-5 rounded-2xl border-2 ${borderCol} bg-white shadow-xs flex flex-col justify-between`;
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-semibold text-slate-400">Limiti: ${f.temperatura_minima}°C &bull; ${f.temperatura_massima}°C</span>
            ${statusBadge}
          </div>
          <h4 class="text-base font-extrabold text-slate-900">${f.nome_frigorifero}</h4>
          <div class="mt-4 flex items-baseline space-x-2">
            <span class="text-3xl font-black ${hasRec ? (isOk ? 'text-slate-900' : 'text-rose-600') : 'text-slate-300'}">
              ${hasRec ? `${Number(f.ultima_temperatura).toFixed(1)}°C` : '--'}
            </span>
            <span class="text-xs text-slate-500">${f.ultima_data ? formatDisplayDateTime(f.ultima_data) : ''}</span>
          </div>
          <p class="text-xs text-slate-500 mt-1">${f.ultimo_operatore ? `Operatore: ${f.ultimo_operatore}` : 'In attesa di registrazione'}</p>
        </div>
        <div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
          <button onclick="quickSelectFridgeForTemp(${f.id})" class="flex-1 py-2 px-3 text-xs font-bold rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 transition-colors">
            Registra Lettura &rarr;
          </button>
          ${userHasPermission('haccp.temp.manage') ? `
          <button onclick="openRenameFridgeModal(${f.id}, '${escapeHtml(f.nome_frigorifero).replace(/'/g, "\\'")}')" class="py-2 px-2.5 text-xs font-bold rounded-xl border border-slate-300 text-slate-700 hover:bg-slate-50 transition-colors" title="Modifica nome">
            Modifica nome
          </button>` : ''}
        </div>
      `;
      container.appendChild(card);
    });

    // Seleziona il primo frigo
    if (cachedFridges.length > 0 && !selFridge.value) {
      selFridge.value = cachedFridges[0].id;
      handleFridgeSelectionForTemp(selFridge);
    }

    // Imposta operatore
    if (currentUser) {
      document.getElementById('temp-operatore').value = currentUser.full_name || currentUser.username;
    }

    setTempEsito('CONFORME');
    loadTemperatureHistory();
  } catch (err) {
    console.error('Errore temperature HACCP:', err);
  }
}

function openRenameFridgeModal(fridgeId, currentName) {
  if (!userHasPermission('haccp.temp.manage')) {
    showToast('Non hai il permesso di modificare i frigoriferi.', 'error');
    return;
  }
  document.getElementById('rename-fridge-id').value = fridgeId;
  document.getElementById('rename-fridge-name').value = currentName || '';
  openModal('modal-rename-fridge');
}

async function handleRenameFridgeSubmit(event) {
  event.preventDefault();
  const fridgeId = parseInt(document.getElementById('rename-fridge-id').value);
  const newName = document.getElementById('rename-fridge-name').value.trim();
  if (!newName) {
    showToast('Inserisci il nuovo nome per il frigorifero.', 'error');
    return;
  }

  try {
    const res = await authFetch(`/api/haccp/temperature/fridges/${fridgeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome: newName })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Errore nella modifica del nome.');
    }
    const data = await res.json();
    closeModal('modal-rename-fridge');
    showToast(data.message || 'Nome frigorifero aggiornato con successo.');
    loadHaccpTemperature();
    loadHaccpAlerts();
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Errore durante la modifica del nome.', 'error');
  }
}

function quickSelectFridgeForTemp(fridgeId) {
  const sel = document.getElementById('temp-select-fridge');
  sel.value = fridgeId;
  handleFridgeSelectionForTemp(sel);
  document.getElementById('card-record-temp').scrollIntoView({ behavior: 'smooth' });
}

function handleFridgeSelectionForTemp(selectEl) {
  if (!selectEl.value) return;
  const opt = selectEl.options[selectEl.selectedIndex];
  const tmin = parseFloat(opt.dataset.tmin);
  const tmax = parseFloat(opt.dataset.tmax);
  // Suggerisci valore centrale tipico se vuoto
  const tempInput = document.getElementById('temp-valore');
  if (!tempInput.value) {
    const defaultVal = !isNaN(tmin) && !isNaN(tmax) ? ((tmin + tmax) / 2).toFixed(1) : '3.0';
    tempInput.value = defaultVal;
  }
}

function adjustTempInput(delta) {
  const input = document.getElementById('temp-valore');
  let current = parseFloat(input.value) || 0.0;
  current = Math.round((current + delta) * 10) / 10;
  input.value = current.toFixed(1);

  // Auto-valuta limiti se possibile
  const sel = document.getElementById('temp-select-fridge');
  if (sel.value) {
    const opt = sel.options[sel.selectedIndex];
    const tmin = parseFloat(opt.dataset.tmin);
    const tmax = parseFloat(opt.dataset.tmax);
    if (!isNaN(tmin) && !isNaN(tmax)) {
      if (current < tmin || current > tmax) {
        setTempEsito('NON_CONFORME');
      } else {
        setTempEsito('CONFORME');
      }
    }
  }
}

function setTempEsito(esito) {
  currentTempEsito = esito;
  const btnC = document.getElementById('btn-esito-c');
  const btnNC = document.getElementById('btn-esito-nc');
  const actionBox = document.getElementById('temp-nc-action-box');
  const actionInput = document.getElementById('temp-azione-correttiva');

  if (esito === 'CONFORME') {
    btnC.className = 'py-4 px-6 rounded-2xl text-lg font-black border-3 border-emerald-500 bg-emerald-50 text-emerald-800 shadow-md transition-all flex items-center justify-center space-x-2';
    btnNC.className = 'py-4 px-6 rounded-2xl text-lg font-bold border-2 border-slate-300 bg-white text-slate-600 hover:bg-slate-50 transition-all flex items-center justify-center space-x-2';
    actionBox.classList.add('hidden');
    actionInput.required = false;
  } else {
    btnNC.className = 'py-4 px-6 rounded-2xl text-lg font-black border-3 border-rose-500 bg-rose-50 text-rose-800 shadow-md transition-all flex items-center justify-center space-x-2';
    btnC.className = 'py-4 px-6 rounded-2xl text-lg font-bold border-2 border-slate-300 bg-white text-slate-600 hover:bg-slate-50 transition-all flex items-center justify-center space-x-2';
    actionBox.classList.remove('hidden');
    actionInput.required = true;
  }
  lucide.createIcons();
}

async function handleRecordTempSubmit(event) {
  event.preventDefault();
  if (!userHasPermission('haccp.temp.record')) {
    showToast('Non hai il permesso di registrare controlli temperatura.', 'error');
    return;
  }

  const fridgeId = parseInt(document.getElementById('temp-select-fridge').value);
  const operatore = document.getElementById('temp-operatore').value.trim();
  const temperatura = parseFloat(document.getElementById('temp-valore').value);
  const azione = document.getElementById('temp-azione-correttiva').value.trim();

  if (!fridgeId) {
    showToast('Seleziona il frigorifero o la cella.', 'error');
    return;
  }

  if (currentTempEsito === 'NON_CONFORME' && !azione) {
    showToast('Per i controlli Non Conformi è obbligatorio specificare l\'azione correttiva.', 'error');
    document.getElementById('temp-azione-correttiva').focus();
    return;
  }

  const payload = {
    sede_id: activeVenueId,
    frigorifero_id: fridgeId,
    temperatura: temperatura,
    esito: currentTempEsito,
    azione_correttiva: currentTempEsito === 'NON_CONFORME' ? azione : null,
    operatore: operatore
  };

  try {
    const res = await authFetch('/api/haccp/temperature/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    showToast(data.message);

    // Reset parziale form
    document.getElementById('temp-azione-correttiva').value = '';
    setTempEsito('CONFORME');

    // Ricarica cards e storico
    loadHaccpTemperature();
    loadHaccpAlerts();
  } catch (err) {
    console.error(err);
  }
}

async function loadTemperatureHistory() {
  const fridgeFilter = document.getElementById('temp-history-fridge-filter').value;
  let url = `/api/haccp/temperature/history?sede_id=${activeVenueId}`;
  if (fridgeFilter) url += `&frigorifero_id=${fridgeFilter}`;

  try {
    const res = await authFetch(url);
    const data = await res.json();
    const tbody = document.getElementById('temp-history-table-body');
    tbody.innerHTML = '';

    if (!data.records || data.records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-slate-400">Nessuna registrazione di temperatura trovata per i filtri selezionati.</td></tr>`;
      return;
    }

    data.records.forEach(r => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition-colors';
      const isC = r.esito === 'CONFORME';
      const esitoBadge = isC
        ? `<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-100 text-emerald-800">C</span>`
        : `<span class="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-100 text-rose-800">NC</span>`;

      tr.innerHTML = `
        <td class="py-2.5 px-4 font-mono text-slate-600">${formatDisplayDateTime(r.data_ora)}</td>
        <td class="py-2.5 px-4 font-bold text-slate-900">${r.frigorifero_nome}</td>
        <td class="py-2.5 px-4 text-center font-mono font-bold text-sm ${isC ? 'text-slate-900' : 'text-rose-600'}">${Number(r.temperatura).toFixed(1)}°C</td>
        <td class="py-2.5 px-4 text-center">${esitoBadge}</td>
        <td class="py-2.5 px-4 text-slate-700">${r.azione_correttiva || '-'}</td>
        <td class="py-2.5 px-4 font-medium text-slate-600">${r.operatore}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

function openNewFridgeModal() {
  document.getElementById('hfridge-name').value = '';
  document.getElementById('hfridge-tmin').value = '0.0';
  document.getElementById('hfridge-tmax').value = '4.0';
  openModal('modal-haccp-fridge');
}

async function handleSaveFridgeSubmit(event) {
  event.preventDefault();
  const payload = {
    sede_id: activeVenueId,
    nome_frigorifero: document.getElementById('hfridge-name').value.trim(),
    temperatura_minima: parseFloat(document.getElementById('hfridge-tmin').value) || 0.0,
    temperatura_massima: parseFloat(document.getElementById('hfridge-tmax').value) || 4.0
  };

  try {
    const res = await authFetch('/api/haccp/temperature/fridges', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    closeModal('modal-haccp-fridge');
    showToast(data.message);
    loadHaccpTemperature();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// 7. HACCP: CAMBIO OLIO FRIGGITRICI
// ==========================================
async function loadHaccpOil() {
  try {
    const res = await authFetch(`/api/haccp/oil/fryers?sede_id=${activeVenueId}`);
    const data = await res.json();
    cachedFryers = data.fryers || [];

    // Mostra bottone configurazione friggitrici se ha permesso
    const btnCfg = document.getElementById('btn-config-fryers');
    if (userHasPermission('haccp.oil.manage')) btnCfg.classList.remove('hidden');
    else btnCfg.classList.add('hidden');

    const container = document.getElementById('fryers-cards-container');
    container.innerHTML = '';

    cachedFryers.forEach(fryer => {
      const card = document.createElement('div');
      const hasChange = !!fryer.ultimo_cambio_data;
      let statusColor = 'border-slate-200 bg-white';
      let statusBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-500">Nessun cambio registrato</span>`;

      if (hasChange) {
        const days = fryer.giorni_da_ultimo_cambio || 0;
        if (days <= 3) {
          statusColor = 'border-emerald-300 bg-emerald-50/20';
          statusBadge = `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">Olio Fresco (${days} gg fa)</span>`;
        } else if (days <= 7) {
          statusColor = 'border-amber-300 bg-amber-50/20';
          statusBadge = `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800">In Uso (${days} gg fa)</span>`;
        } else {
          statusColor = 'border-rose-300 bg-rose-50/30';
          statusBadge = `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">Da Sostituire (${days} gg fa)</span>`;
        }
      }

      card.className = `p-6 rounded-2xl border-2 ${statusColor} shadow-sm flex flex-col justify-between`;
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">${fryer.codice_identificativo}</span>
            ${statusBadge}
          </div>
          <h4 class="text-xl font-black text-slate-900">${fryer.nome_friggitrice}</h4>
          <p class="text-xs text-slate-500 mt-1">${fryer.capacita_litri ? `Capacità vasca: ${fryer.capacita_litri}L` : 'Vasca standard'}</p>

          <div class="mt-5 p-4 rounded-xl bg-white border border-slate-200 space-y-1 text-xs">
            <div class="flex justify-between">
              <span class="text-slate-500">Ultimo cambio olio:</span>
              <strong class="text-slate-800">${hasChange ? `${fryer.ultimo_cambio_data} ore ${fryer.ultimo_cambio_ora || ''}` : 'Mai'}</strong>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Addetto al cambio:</span>
              <span class="font-medium text-slate-700">${fryer.ultimo_operatore || '--'}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">Tipologia / Note:</span>
              <span class="text-slate-700 truncate max-w-[200px]">${fryer.ultime_note || 'Olio frittura standard'}</span>
            </div>
          </div>
        </div>

        <div class="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between">
          <button onclick="openRecordOilModal(${fryer.id}, '${fryer.nome_friggitrice.replace(/'/g, "\\'")}')"
            class="w-full py-3 px-4 rounded-xl text-sm font-bold text-white bg-slate-900 hover:bg-slate-800 active:bg-slate-950 transition-all flex items-center justify-center space-x-2 shadow-sm">
            <i data-lucide="droplet" class="w-4 h-4 text-amber-400"></i>
            <span>Registra Nuovo Cambio Olio</span>
          </button>
        </div>
      `;
      container.appendChild(card);
    });

    loadHaccpOilHistory();
    lucide.createIcons();
  } catch (err) {
    console.error('Errore cambio olio:', err);
  }
}

function openRecordOilModal(fryerId, fryerName) {
  if (!userHasPermission('haccp.oil.record')) {
    showToast('Non hai il permesso di registrare il cambio olio.', 'error');
    return;
  }

  document.getElementById('oil-modal-fryer-id').value = fryerId;
  document.getElementById('oil-modal-fryer-name').textContent = fryerName;

  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  document.getElementById('oil-modal-date').value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  document.getElementById('oil-modal-time').value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  document.getElementById('oil-modal-operator').value = currentUser ? currentUser.full_name : '';
  document.getElementById('oil-modal-notes').value = '';

  openModal('modal-record-oil');
}

async function handleRecordOilSubmit(event) {
  event.preventDefault();
  const fryerId = parseInt(document.getElementById('oil-modal-fryer-id').value);
  const dataCambio = document.getElementById('oil-modal-date').value;
  const oraCambio = document.getElementById('oil-modal-time').value;
  const operatore = document.getElementById('oil-modal-operator').value.trim();
  const note = document.getElementById('oil-modal-notes').value.trim();

  const payload = {
    sede_id: activeVenueId,
    friggitrice_id: fryerId,
    data_cambio: dataCambio,
    ora_cambio: oraCambio,
    operatore: operatore,
    note: note || null
  };

  try {
    const res = await authFetch('/api/haccp/oil/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    closeModal('modal-record-oil');
    showToast(data.message);
    loadHaccpOil();
    loadHaccpAlerts();
  } catch (err) {
    console.error(err);
  }
}

async function loadHaccpOilHistory() {
  try {
    const res = await authFetch(`/api/haccp/oil/history?sede_id=${activeVenueId}`);
    const data = await res.json();
    const tbody = document.getElementById('oil-history-table-body');
    tbody.innerHTML = '';

    document.getElementById('oil-history-count').textContent = `${data.count} cambi registrati`;

    if (!data.records || data.records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-slate-400">Nessun cambio olio registrato nello storico.</td></tr>`;
      return;
    }

    data.records.forEach(r => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition-colors';
      tr.innerHTML = `
        <td class="py-2.5 px-4 font-bold text-slate-900">${r.friggitrice_nome}</td>
        <td class="py-2.5 px-4 font-mono font-medium text-slate-700">${r.data_cambio}</td>
        <td class="py-2.5 px-4 font-mono text-slate-600">${r.ora_cambio || '--:--'}</td>
        <td class="py-2.5 px-4 font-semibold text-slate-800">${r.operatore}</td>
        <td class="py-2.5 px-4 text-slate-600">${r.note || '-'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

function openConfigureFryersModal() {
  const container = document.getElementById('fryers-rename-list');
  container.innerHTML = '';

  cachedFryers.forEach(f => {
    const row = document.createElement('div');
    row.className = 'p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between space-x-2';
    row.innerHTML = `
      <div class="flex-1">
        <label class="block text-[11px] font-bold text-slate-500 uppercase">${f.codice_identificativo}</label>
        <input type="text" id="rename-fryer-${f.id}" value="${f.nome_friggitrice}" class="w-full text-sm font-semibold px-2.5 py-1.5 rounded-lg border border-slate-300">
      </div>
      <button onclick="saveFryerRename(${f.id})" class="px-3 py-2 text-xs font-bold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 mt-4">
        Salva
      </button>
    `;
    container.appendChild(row);
  });

  openModal('modal-config-fryers');
}

async function saveFryerRename(fryerId) {
  const newName = document.getElementById(`rename-fryer-${fryerId}`).value.trim();
  if (!newName) return;

  try {
    const res = await authFetch(`/api/haccp/oil/fryers/${fryerId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome_friggitrice: newName })
    });
    const data = await res.json();
    showToast(data.message);
    loadHaccpOil();
    loadHaccpAlerts();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// 8. HACCP: PULIZIA SETTIMANALE CAPPA
// ==========================================
let currentWeekIso = null;

async function loadHaccpHood() {
  try {
    const res = await authFetch(`/api/haccp/hood/status?sede_id=${activeVenueId}`);
    const data = await res.json();
    currentWeekIso = data.week_iso;

    const card = document.getElementById('hood-current-week-card');
    const isDone = data.status === 'ESEGUITA';
    const rec = data.current_record;

    if (isDone) {
      card.className = 'p-6 rounded-2xl border-2 border-emerald-300 bg-emerald-50/30 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4';
      card.innerHTML = `
        <div>
          <div class="flex items-center space-x-2">
            <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">✅ ESEGUITA</span>
            <span class="text-xs font-mono text-slate-500">${data.week_iso} (Settimana ${data.week_number} del ${data.year})</span>
          </div>
          <h4 class="text-xl font-black text-slate-900 mt-1">Pulizia Cappa Settimanale Eseguita</h4>
          <p class="text-xs text-slate-600 mt-1">
            Effettuata il <strong>${rec.data_pulizia}</strong> ore <strong>${rec.ora_pulizia || '--:--'}</strong> da <strong>${rec.operatore}</strong>
          </p>
          <p class="text-xs text-slate-500 mt-0.5">${rec.note ? `Note: ${rec.note}` : 'Filtri lavati e canali sgrassati secondo procedura HACCP.'}</p>
        </div>
        <div>
          <button onclick="openRecordHoodModal('${data.week_iso}')" class="px-4 py-2.5 rounded-xl text-xs font-bold text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 transition-colors shadow-xs">
            Aggiorna Registrazione
          </button>
        </div>
      `;
    } else {
      card.className = 'p-6 rounded-2xl border-2 border-amber-300 bg-amber-50/40 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4';
      card.innerHTML = `
        <div>
          <div class="flex items-center space-x-2">
            <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800">⚠️ DA FARE</span>
            <span class="text-xs font-mono text-slate-500">${data.week_iso} (Settimana ${data.week_number} del ${data.year})</span>
          </div>
          <h4 class="text-xl font-black text-slate-900 mt-1">Pulizia Cappa per la Settimana Corrente in Sospeso</h4>
          <p class="text-xs text-slate-600 mt-1">Sanificazione e lavaggio filtri della cappa d'aspirazione obbligatori da piano HACCP.</p>
        </div>
        <div>
          <button onclick="openRecordHoodModal('${data.week_iso}')" class="w-full md:w-auto px-6 py-3.5 rounded-xl text-sm font-bold text-white bg-slate-900 hover:bg-slate-800 transition-all shadow-md flex items-center justify-center space-x-2">
            <i data-lucide="check-circle" class="w-4 h-4 text-emerald-400"></i>
            <span>Registra Pulizia Eseguita</span>
          </button>
        </div>
      `;
    }

    // Carica storico settimane precedenti
    loadHaccpHoodHistory();
    lucide.createIcons();
  } catch (err) {
    console.error('Errore stato cappa:', err);
  }
}

function openRecordHoodModal(weekIso) {
  if (!userHasPermission('haccp.hood.record')) {
    showToast('Non hai il permesso di registrare la pulizia della cappa.', 'error');
    return;
  }

  document.getElementById('hood-modal-week-label').textContent = weekIso || currentWeekIso;
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  document.getElementById('hood-modal-date').value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  document.getElementById('hood-modal-time').value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  document.getElementById('hood-modal-operator').value = currentUser ? currentUser.full_name : '';
  document.getElementById('hood-modal-notes').value = '';

  openModal('modal-record-hood');
}

async function handleRecordHoodSubmit(event) {
  event.preventDefault();
  const weekIso = document.getElementById('hood-modal-week-label').textContent;
  const dataPulizia = document.getElementById('hood-modal-date').value;
  const oraPulizia = document.getElementById('hood-modal-time').value;
  const operatore = document.getElementById('hood-modal-operator').value.trim();
  const note = document.getElementById('hood-modal-notes').value.trim();

  const payload = {
    sede_id: activeVenueId,
    settimana_riferimento: weekIso,
    data_pulizia: dataPulizia,
    ora_pulizia: oraPulizia,
    operatore: operatore,
    note: note || null
  };

  try {
    const res = await authFetch('/api/haccp/hood/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    closeModal('modal-record-hood');
    showToast(data.message);
    loadHaccpHood();
    loadHaccpAlerts();
  } catch (err) {
    console.error(err);
  }
}

async function loadHaccpHoodHistory() {
  try {
    const res = await authFetch(`/api/haccp/hood/history?sede_id=${activeVenueId}`);
    const data = await res.json();
    const tbody = document.getElementById('hood-history-table-body');
    tbody.innerHTML = '';

    if (!data.records || data.records.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-slate-400">Nessuna registrazione precedente per la pulizia cappa.</td></tr>`;
      return;
    }

    data.records.forEach(r => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition-colors';
      tr.innerHTML = `
        <td class="py-2.5 px-4 font-mono font-bold text-slate-900">${r.settimana_riferimento}</td>
        <td class="py-2.5 px-4 font-mono text-slate-700">${r.data_pulizia} ${r.ora_pulizia ? `ore ${r.ora_pulizia}` : ''}</td>
        <td class="py-2.5 px-4 font-semibold text-slate-800">${r.operatore}</td>
        <td class="py-2.5 px-4 text-slate-600">${r.note || 'Pulizia regolare e sanificazione'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// 8.1 HACCP: REGISTRI PULIZIE (MURI, VETRI, MAGAZZINO)
// ==========================================
const CLEANING_CONFIG = {
  muri: {
    label: 'Pulizia muri e pareti lavabili',
    tab: 'cleaning_walls',
    perm: 'haccp.cleaning.walls',
    frequencyText: 'Mensile (1 mese solare esatto con arrotondamento fine mese)',
    btnId: 'btn-record-cleaning-walls',
    cardId: 'status-card-cleaning-muri',
    tableId: 'cleaning-muri-table-body',
    countId: 'cleaning-muri-count'
  },
  vetri: {
    label: 'Pulizia vetri e infissi',
    tab: 'cleaning_windows',
    perm: 'haccp.cleaning.windows',
    frequencyText: 'Mensile (1 mese solare esatto con arrotondamento fine mese)',
    btnId: 'btn-record-cleaning-windows',
    cardId: 'status-card-cleaning-vetri',
    tableId: 'cleaning-vetri-table-body',
    countId: 'cleaning-vetri-count'
  },
  magazzino: {
    label: 'Pulizia magazzino e scorte',
    tab: 'cleaning_warehouse',
    perm: 'haccp.cleaning.warehouse',
    frequencyText: 'Settimanale (frequenza standard: 7 giorni)',
    btnId: 'btn-record-cleaning-warehouse',
    cardId: 'status-card-cleaning-magazzino',
    tableId: 'cleaning-magazzino-table-body',
    countId: 'cleaning-magazzino-count'
  }
};

async function loadHaccpCleaning(tipo) {
  const cfg = CLEANING_CONFIG[tipo];
  if (!cfg) return;

  // Mostra pulsante registrazione se ha permesso
  const btnRec = document.getElementById(cfg.btnId);
  if (btnRec) {
    if (userHasPermission(`${cfg.perm}.record`)) btnRec.classList.remove('hidden');
    else btnRec.classList.add('hidden');
  }

  try {
    let histUrl = `/api/haccp/cleaning/history?sede_id=${activeVenueId}&tipo_pulizia=${tipo}`;
    const dFrom = document.getElementById(`cleaning-${tipo}-date-from`)?.value;
    const dTo = document.getElementById(`cleaning-${tipo}-date-to`)?.value;
    if (dFrom) histUrl += `&date_from=${encodeURIComponent(dFrom)}`;
    if (dTo) histUrl += `&date_to=${encodeURIComponent(dTo)}`;

    const [statusRes, histRes] = await Promise.all([
      authFetch(`/api/haccp/cleaning/status?sede_id=${activeVenueId}&tipo_pulizia=${tipo}`),
      authFetch(histUrl)
    ]);

    const statusData = await statusRes.json();
    const histData = await histRes.json();

    // Render Status Card
    const cardEl = document.getElementById(cfg.cardId);
    if (cardEl) {
      if (!statusData.has_record) {
        cardEl.className = 'p-5 rounded-2xl border-2 border-rose-300 bg-rose-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4';
        cardEl.innerHTML = `
          <div>
            <div class="flex items-center space-x-2">
              <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">⚠️ PRIMA REGISTRAZIONE</span>
              <span class="text-xs text-slate-500">${cfg.frequencyText}</span>
            </div>
            <h4 class="text-lg font-black text-slate-900 mt-1">${cfg.label}: Prima registrazione da effettuare</h4>
            <p class="text-xs text-slate-600 mt-0.5">Non sono presenti registrazioni storiche per questa sanificazione nel locale selezionato.</p>
          </div>
          ${userHasPermission(`${cfg.perm}.record`) ? `
            <button onclick="openRecordCleaningModal('${tipo}')" class="px-5 py-3 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 transition-all shadow-md flex items-center justify-center space-x-2 flex-shrink-0">
              <i data-lucide="plus-circle" class="w-4 h-4 text-emerald-400"></i>
              <span>Esegui Prima Registrazione</span>
            </button>
          ` : ''}
        `;
      } else {
        const isOverdue = statusData.is_overdue;
        const borderCol = isOverdue ? 'border-rose-300 bg-rose-50/40' : 'border-emerald-300 bg-emerald-50/30';
        const badge = isOverdue
          ? `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">⚠️ SCADUTA DA ${statusData.giorni_scaduti} GG</span>`
          : `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">CONFORME HACCP</span>`;

        cardEl.className = `p-5 rounded-2xl border-2 ${borderCol} flex flex-col sm:flex-row sm:items-center justify-between gap-4`;
        cardEl.innerHTML = `
          <div>
            <div class="flex items-center space-x-2">
              ${badge}
              <span class="text-xs text-slate-500">${cfg.frequencyText}</span>
            </div>
            <h4 class="text-lg font-black text-slate-900 mt-1">${cfg.label}</h4>
            <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700">
              <div>Ultima esecuzione: <strong class="font-mono text-slate-900">${formatDisplayDateTime(`${statusData.ultima_data} ${statusData.ultima_ora || '00:00'}`)}</strong></div>
              <div>Addetto: <strong class="text-slate-900">${escapeHtml(statusData.ultimo_operatore || '--')}</strong></div>
              <div>Prossima scadenza: <strong class="font-mono text-emerald-900 font-black">${statusData.prossima_scadenza || '--'}</strong></div>
            </div>
          </div>
          ${userHasPermission(`${cfg.perm}.record`) ? `
            <button onclick="openRecordCleaningModal('${tipo}')" class="px-5 py-3 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 transition-all shadow-md flex items-center justify-center space-x-2 flex-shrink-0">
              <i data-lucide="check-circle" class="w-4 h-4 text-emerald-400"></i>
              <span>Registra Pulizia Eseguita</span>
            </button>
          ` : ''}
        `;
      }
    }

    // Render Table
    const tbody = document.getElementById(cfg.tableId);
    if (tbody) {
      tbody.innerHTML = '';
      const countEl = document.getElementById(cfg.countId);
      if (countEl) countEl.textContent = `${histData.count || (histData.records ? histData.records.length : 0)} registrazioni`;

      if (!histData.records || histData.records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-slate-400">Nessuna registrazione precedente per questa pulizia.</td></tr>`;
      } else {
        histData.records.forEach(r => {
          const tr = document.createElement('tr');
          tr.className = 'hover:bg-slate-50 transition-colors';
          tr.innerHTML = `
            <td class="py-2.5 px-4 font-mono font-bold text-slate-900">${r.data_esecuzione} ${r.ora_esecuzione ? `ore ${r.ora_esecuzione}` : ''}</td>
            <td class="py-2.5 px-4 font-semibold text-slate-800">${escapeHtml(r.operatore)}</td>
            <td class="py-2.5 px-4 font-mono font-bold text-emerald-900 bg-emerald-50/40">${r.prossima_scadenza || '--'}</td>
            <td class="py-2.5 px-4 text-slate-600">${escapeHtml(r.note || 'Sanificazione conforme')}</td>
          `;
          tbody.appendChild(tr);
        });
      }
    }

    lucide.createIcons();
  } catch (err) {
    console.error(`Errore caricamento pulizia ${tipo}:`, err);
  }
}

function resetCleaningDateFilter(tipo) {
  const fromEl = document.getElementById(`cleaning-${tipo}-date-from`);
  const toEl = document.getElementById(`cleaning-${tipo}-date-to`);
  if (fromEl) fromEl.value = '';
  if (toEl) toEl.value = '';
  loadHaccpCleaning(tipo);
}

function openRecordCleaningModal(tipo) {
  const cfg = CLEANING_CONFIG[tipo];
  if (!cfg) return;

  if (!userHasPermission(`${cfg.perm}.record`)) {
    showToast('Non hai il permesso di registrare questa pulizia.', 'error');
    return;
  }

  document.getElementById('cleaning-modal-tipo').value = tipo;
  document.getElementById('modal-cleaning-title').textContent = `Registra ${cfg.label}`;
  document.getElementById('cleaning-modal-info').innerHTML = `
    <div class="flex items-center space-x-1.5 text-xs text-slate-700">
      <i data-lucide="info" class="w-4 h-4 text-indigo-500"></i>
      <span>Frequenza prevista da piano HACCP: <strong>${cfg.frequencyText}</strong>. La prossima scadenza viene calcolata e salvata automaticamente.</span>
    </div>
  `;

  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  document.getElementById('cleaning-modal-date').value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  document.getElementById('cleaning-modal-time').value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  document.getElementById('cleaning-modal-operator').value = currentUser ? (currentUser.full_name || currentUser.username) : '';
  document.getElementById('cleaning-modal-notes').value = '';

  openModal('modal-record-general-cleaning');
  lucide.createIcons();
}

async function handleRecordGeneralCleaningSubmit(event) {
  event.preventDefault();
  const tipo = document.getElementById('cleaning-modal-tipo').value;
  const cfg = CLEANING_CONFIG[tipo];
  if (!cfg) return;

  const dataExec = document.getElementById('cleaning-modal-date').value;
  const oraExec = document.getElementById('cleaning-modal-time').value;
  const operatore = document.getElementById('cleaning-modal-operator').value.trim();
  const note = document.getElementById('cleaning-modal-notes').value.trim();

  if (!operatore) {
    showToast('Inserisci il nome dell\'operatore.', 'error');
    return;
  }

  const payload = {
    sede_id: activeVenueId,
    tipo_pulizia: tipo,
    data_esecuzione: dataExec,
    ora_esecuzione: oraExec,
    operatore: operatore,
    note: note || null
  };

  try {
    const res = await authFetch('/api/haccp/cleaning/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Errore nel salvataggio della pulizia.');
    }

    const data = await res.json();
    closeModal('modal-record-general-cleaning');
    showToast(data.message || 'Pulizia salvata con successo.');
    loadHaccpCleaning(tipo);
    loadHaccpAlerts();
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Errore durante la registrazione.', 'error');
  }
}

// ==========================================
// 8.2 HACCP: MONITORAGGIO INFESTANTI (8 VOCI SEQUENZIALI)
// ==========================================
async function loadHaccpPests() {
  const btnStart = document.getElementById('btn-start-pest-inspection');
  if (btnStart) {
    if (userHasPermission('haccp.pests.record')) btnStart.classList.remove('hidden');
    else btnStart.classList.add('hidden');
  }

  try {
    let histUrl = `/api/haccp/pests/history?sede_id=${activeVenueId}`;
    const dFrom = document.getElementById('pests-date-from')?.value;
    const dTo = document.getElementById('pests-date-to')?.value;
    if (dFrom) histUrl += `&date_from=${encodeURIComponent(dFrom)}`;
    if (dTo) histUrl += `&date_to=${encodeURIComponent(dTo)}`;

    const [statusRes, histRes] = await Promise.all([
      authFetch(`/api/haccp/pests/status?sede_id=${activeVenueId}`),
      authFetch(histUrl)
    ]);

    const statusData = await statusRes.json();
    const histData = await histRes.json();
    cachedPestInspections = histData.records || [];

    // Render Status Card
    const cardEl = document.getElementById('status-card-pests');
    if (cardEl) {
      if (!statusData.has_record) {
        cardEl.className = 'p-5 rounded-2xl border-2 border-rose-300 bg-rose-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4';
        cardEl.innerHTML = `
          <div>
            <div class="flex items-center space-x-2">
              <span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">⚠️ PRIMA REGISTRAZIONE</span>
              <span class="text-xs text-slate-500">Cadenza: 1 mese solare</span>
            </div>
            <h4 class="text-lg font-black text-slate-900 mt-1">Monitoraggio infestanti: Prima registrazione da effettuare</h4>
            <p class="text-xs text-slate-600 mt-0.5">Nessun controllo delle 8 voci obbligatorie è ancora stato registrato per questo locale.</p>
          </div>
          ${userHasPermission('haccp.pests.record') ? `
            <button onclick="startNewPestInspection()" class="px-5 py-3 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 transition-all shadow-md flex items-center justify-center space-x-2 flex-shrink-0">
              <i data-lucide="clipboard-check" class="w-4 h-4 text-emerald-400"></i>
              <span>Inizia Prima Ispezione</span>
            </button>
          ` : ''}
        `;
      } else {
        const isOverdue = statusData.is_overdue;
        const borderCol = isOverdue ? 'border-rose-300 bg-rose-50/40' : 'border-emerald-300 bg-emerald-50/30';
        const badge = isOverdue
          ? `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">⚠️ SCADUTO DA ${statusData.giorni_scaduti} GG</span>`
          : `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">CONFORME HACCP</span>`;
        const outcomeBadge = statusData.has_presenze
          ? `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">Presenze rilevate nell'ultimo controllo</span>`
          : `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">Nessuna presenza rilevata (Regolare)</span>`;

        cardEl.className = `p-5 rounded-2xl border-2 ${borderCol} flex flex-col sm:flex-row sm:items-center justify-between gap-4`;
        cardEl.innerHTML = `
          <div>
            <div class="flex items-center space-x-2">
              ${badge}
              ${outcomeBadge}
            </div>
            <h4 class="text-lg font-black text-slate-900 mt-1">Monitoraggio Infestanti e Roditori</h4>
            <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700">
              <div>Ultimo controllo: <strong class="font-mono text-slate-900">${formatDisplayDateTime(`${statusData.ultima_data} ${statusData.ultima_ora || '00:00'}`)}</strong></div>
              <div>Operatore: <strong class="text-slate-900">${escapeHtml(statusData.ultimo_operatore || '--')}</strong></div>
              <div>Prossima scadenza: <strong class="font-mono text-emerald-900 font-black">${statusData.prossima_scadenza || '--'}</strong></div>
            </div>
          </div>
          ${userHasPermission('haccp.pests.record') ? `
            <button onclick="startNewPestInspection()" class="px-5 py-3 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 transition-all shadow-md flex items-center justify-center space-x-2 flex-shrink-0">
              <i data-lucide="plus-circle" class="w-4 h-4 text-emerald-400"></i>
              <span>Nuovo Controllo Mensile</span>
            </button>
          ` : ''}
        `;
      }
    }

    // Render Table
    const tbody = document.getElementById('pests-history-table-body');
    if (tbody) {
      tbody.innerHTML = '';
      const countEl = document.getElementById('pests-history-count');
      if (countEl) countEl.textContent = `${histData.count || cachedPestInspections.length} controlli`;

      if (!cachedPestInspections || cachedPestInspections.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-slate-400">Nessun controllo registrato.</td></tr>`;
      } else {
        cachedPestInspections.forEach(r => {
          const tr = document.createElement('tr');
          tr.className = 'hover:bg-slate-50 transition-colors';
          const outcomeBadge = r.has_presenze
            ? `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">⚠️ Rilevata presenza</span>`
            : `<span class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">✓ Regolare (Assenza)</span>`;

          tr.innerHTML = `
            <td class="py-2.5 px-4 font-mono font-bold text-slate-900">${r.data_controllo} ${r.ora_controllo ? `ore ${r.ora_controllo}` : ''}</td>
            <td class="py-2.5 px-4 font-semibold text-slate-800">${escapeHtml(r.operatore)}</td>
            <td class="py-2.5 px-4 text-center">${outcomeBadge}</td>
            <td class="py-2.5 px-4 font-mono font-bold text-emerald-900 bg-emerald-50/40">${r.prossima_scadenza || '--'}</td>
            <td class="py-2.5 px-4 text-slate-600 truncate max-w-[200px]">${escapeHtml(r.note_generali || '--')}</td>
            <td class="py-2.5 px-4 text-right">
              <button onclick="openPestInspectionDetail(${r.id})" class="px-2.5 py-1 text-xs font-bold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300">
                Dettaglio
              </button>
            </td>
          `;
          tbody.appendChild(tr);
        });
      }
    }

    lucide.createIcons();
  } catch (err) {
    console.error('Errore monitoraggio infestanti:', err);
  }
}

function resetPestsDateFilter() {
  const fromEl = document.getElementById('pests-date-from');
  const toEl = document.getElementById('pests-date-to');
  if (fromEl) fromEl.value = '';
  if (toEl) toEl.value = '';
  loadHaccpPests();
}

function startNewPestInspection() {
  if (!userHasPermission('haccp.pests.record')) {
    showToast('Non hai il permesso di registrare il controllo infestanti.', 'error');
    return;
  }

  pestWizardState = {
    currentStep: 1,
    answers: {},
    isDirty: true
  };

  const container = document.getElementById('pest-wizard-container');
  if (container) {
    container.classList.remove('hidden');
    container.scrollIntoView({ behavior: 'smooth' });
  }

  renderPestWizardStep(1);
}

function cancelPestInspection() {
  pestWizardState = { currentStep: 1, answers: {}, isDirty: false };
  const container = document.getElementById('pest-wizard-container');
  if (container) container.classList.add('hidden');
}

function renderPestWizardStep(step) {
  const total = VOCI_INFESTANTI_ORDINE.length; // 8
  const title = VOCI_INFESTANTI_ORDINE[step - 1];

  document.getElementById('pest-wizard-step-label').textContent = `Voce ${step} di ${total}`;
  document.getElementById('pest-wizard-item-title').textContent = title;
  document.getElementById('pest-wizard-item-target').textContent = title;

  const percent = Math.round((step / total) * 100);
  document.getElementById('pest-wizard-progress-percent').textContent = `${percent}%`;
  document.getElementById('pest-wizard-progress-bar').style.width = `${(step / total) * 100}%`;

  // Resetta pulsanti touch a stato neutro
  const btnAssenza = document.getElementById('pest-btn-assenza');
  const btnPresenza = document.getElementById('pest-btn-presenza');
  btnAssenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-2 border-slate-300 bg-white text-slate-700 hover:border-emerald-500 hover:bg-emerald-50 transition-all flex items-center justify-center space-x-2';
  btnPresenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-2 border-slate-300 bg-white text-slate-700 hover:border-rose-500 hover:bg-rose-50 transition-all flex items-center justify-center space-x-2';

  // Campi presenza
  const presFields = document.getElementById('pest-presence-fields');
  presFields.classList.add('hidden');
  document.getElementById('pest-input-zona').value = '';
  document.getElementById('pest-input-note').value = '';
  document.getElementById('pest-input-azione').value = '';

  // Se risposta già presente in stato per questo step, ripristinala
  const existing = pestWizardState.answers[step];
  if (existing) {
    if (existing.esito === 'ASSENZA') {
      btnAssenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-3 border-emerald-500 bg-emerald-50 text-emerald-800 transition-all flex items-center justify-center space-x-2 shadow-xs';
    } else if (existing.esito === 'PRESENZA') {
      btnPresenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-3 border-rose-500 bg-rose-50 text-rose-800 transition-all flex items-center justify-center space-x-2 shadow-xs';
      presFields.classList.remove('hidden');
      document.getElementById('pest-input-zona').value = existing.zona || '';
      document.getElementById('pest-input-note').value = existing.note || '';
      document.getElementById('pest-input-azione').value = existing.azione || '';
    }
  }

  // Navigazione wizard
  const btnPrev = document.getElementById('pest-wizard-btn-prev');
  if (step > 1) btnPrev.classList.remove('hidden');
  else btnPrev.classList.add('hidden');

  document.getElementById('pest-wizard-question-pane').classList.remove('hidden');
  document.getElementById('pest-wizard-summary-pane').classList.add('hidden');
  document.getElementById('pest-wizard-btn-next').classList.remove('hidden');
  document.getElementById('pest-wizard-btn-save').classList.add('hidden');

  lucide.createIcons();
}

function setPestAnswer(esito) {
  const btnAssenza = document.getElementById('pest-btn-assenza');
  const btnPresenza = document.getElementById('pest-btn-presenza');
  const presFields = document.getElementById('pest-presence-fields');

  if (esito === 'ASSENZA') {
    btnAssenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-3 border-emerald-500 bg-emerald-50 text-emerald-800 transition-all flex items-center justify-center space-x-2 shadow-xs';
    btnPresenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-2 border-slate-300 bg-white text-slate-700 hover:border-rose-500 hover:bg-rose-50 transition-all flex items-center justify-center space-x-2';
    presFields.classList.add('hidden');
  } else if (esito === 'PRESENZA') {
    btnPresenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-3 border-rose-500 bg-rose-50 text-rose-800 transition-all flex items-center justify-center space-x-2 shadow-xs';
    btnAssenza.className = 'py-5 px-6 rounded-2xl text-lg font-black border-2 border-slate-300 bg-white text-slate-700 hover:border-emerald-500 hover:bg-emerald-50 transition-all flex items-center justify-center space-x-2';
    presFields.classList.remove('hidden');
    document.getElementById('pest-input-zona').focus();
  }

  // Memorizza temporaneamente nello stato
  const step = pestWizardState.currentStep;
  if (!pestWizardState.answers[step]) pestWizardState.answers[step] = {};
  pestWizardState.answers[step].esito = esito;
}

function pestWizardNextStep() {
  const step = pestWizardState.currentStep;

  if (step <= 8) {
    const curAns = pestWizardState.answers[step];
    if (!curAns || !curAns.esito) {
      showToast('Seleziona Assenza o Presenza per questa voce.', 'error');
      return;
    }

    if (curAns.esito === 'PRESENZA') {
      const zona = document.getElementById('pest-input-zona').value.trim();
      const note = document.getElementById('pest-input-note').value.trim();
      const azione = document.getElementById('pest-input-azione').value.trim();

      if (!zona) {
        showToast('La zona del ritrovamento è obbligatoria in caso di presenza.', 'error');
        document.getElementById('pest-input-zona').focus();
        return;
      }
      if (!azione) {
        showToast('L\'azione intrapresa o da intraprendere è obbligatoria in caso di presenza.', 'error');
        document.getElementById('pest-input-azione').focus();
        return;
      }

      curAns.zona = zona;
      curAns.note = note;
      curAns.azione = azione;
    } else {
      curAns.zona = '';
      curAns.note = '';
      curAns.azione = '';
    }

    if (step < 8) {
      pestWizardState.currentStep = step + 1;
      renderPestWizardStep(step + 1);
      return;
    } else {
      // Step 8 completato -> Passa a Step 9 (Riepilogo finale)
      pestWizardState.currentStep = 9;
      renderPestWizardSummary();
      return;
    }
  }
}

function pestWizardPrevStep() {
  const step = pestWizardState.currentStep;
  if (step === 9) {
    pestWizardState.currentStep = 8;
    renderPestWizardStep(8);
  } else if (step > 1) {
    pestWizardState.currentStep = step - 1;
    renderPestWizardStep(step - 1);
  }
}

function renderPestWizardSummary() {
  document.getElementById('pest-wizard-step-label').textContent = 'Riepilogo Finale (9 di 9)';
  document.getElementById('pest-wizard-item-title').textContent = 'Conferma Ispezione Mensile 8 Voci';
  document.getElementById('pest-wizard-progress-percent').textContent = '100%';
  document.getElementById('pest-wizard-progress-bar').style.width = '100%';

  document.getElementById('pest-wizard-question-pane').classList.add('hidden');
  document.getElementById('pest-wizard-summary-pane').classList.remove('hidden');
  document.getElementById('pest-wizard-btn-next').classList.add('hidden');
  document.getElementById('pest-wizard-btn-save').classList.remove('hidden');
  document.getElementById('pest-wizard-btn-prev').classList.remove('hidden');

  // Precompila operatore e data/ora
  document.getElementById('pest-summary-operator').value = currentUser ? (currentUser.full_name || currentUser.username) : '';
  document.getElementById('pest-summary-datetime').value = formatForDatetimeLocal(new Date());

  // Popola tabella riepilogo delle 8 voci
  const tbody = document.getElementById('pest-summary-items-body');
  tbody.innerHTML = '';

  VOCI_INFESTANTI_ORDINE.forEach((voce, idx) => {
    const num = idx + 1;
    const ans = pestWizardState.answers[num] || { esito: 'ASSENZA' };
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-50 transition-colors';

    let badge = `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">Assenza</span>`;
    let details = '<span class="text-slate-400">Nessuna traccia riscontrata</span>';

    if (ans.esito === 'PRESENZA') {
      badge = `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">⚠️ Presenza</span>`;
      details = `<strong>Zona:</strong> ${escapeHtml(ans.zona || '--')}<br><strong>Azione:</strong> ${escapeHtml(ans.azione || '--')}${ans.note ? `<br><em>Note: ${escapeHtml(ans.note)}</em>` : ''}`;
    }

    tr.innerHTML = `
      <td class="py-2 px-3 font-bold text-slate-500">${num}</td>
      <td class="py-2 px-3 font-bold text-slate-900">${voce}</td>
      <td class="py-2 px-3 text-center">${badge}</td>
      <td class="py-2 px-3 text-slate-700 text-xs">${details}</td>
      <td class="py-2 px-3 text-right">
        <button type="button" onclick="jumpToPestWizardStep(${num})" class="text-xs font-semibold text-indigo-600 hover:text-indigo-800 underline">
          Modifica
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  lucide.createIcons();
}

function jumpToPestWizardStep(stepNum) {
  pestWizardState.currentStep = stepNum;
  renderPestWizardStep(stepNum);
}

async function savePestInspection() {
  const op = document.getElementById('pest-summary-operator').value.trim();
  const dtVal = document.getElementById('pest-summary-datetime').value;
  const generalNotes = document.getElementById('pest-summary-general-notes').value.trim();

  if (!op) {
    showToast('Inserisci il nome dell\'operatore.', 'error');
    return;
  }
  if (!dtVal) {
    showToast('Seleziona la data e l\'ora del controllo.', 'error');
    return;
  }

  // Verifica che tutte le 8 risposte siano presenti
  const rispostePayload = [];
  for (let i = 1; i <= 8; i++) {
    const ans = pestWizardState.answers[i];
    if (!ans || !ans.esito) {
      showToast(`Manca la risposta per la voce ${i}: ${VOCI_INFESTANTI_ORDINE[i - 1]}`, 'error');
      jumpToPestWizardStep(i);
      return;
    }
    rispostePayload.push({
      voce: VOCI_INFESTANTI_ORDINE[i - 1],
      esito: ans.esito,
      zona: ans.zona || '',
      note: ans.note || '',
      azione: ans.azione || ''
    });
  }

  const dtObj = new Date(dtVal);
  const pad = (n) => String(n).padStart(2, '0');
  const dStr = `${dtObj.getFullYear()}-${pad(dtObj.getMonth() + 1)}-${pad(dtObj.getDate())}`;
  const tStr = `${pad(dtObj.getHours())}:${pad(dtObj.getMinutes())}`;

  const payload = {
    sede_id: activeVenueId,
    data_controllo: dStr,
    ora_controllo: tStr,
    operatore: op,
    note_generali: generalNotes || null,
    risposte: rispostePayload
  };

  const saveBtn = document.getElementById('pest-wizard-btn-save');
  if (saveBtn) saveBtn.disabled = true;

  try {
    const res = await authFetch('/api/haccp/pests/record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Errore nel salvataggio dell\'ispezione.');
    }

    const data = await res.json();
    cancelPestInspection();
    showToast(data.message || 'Ispezione infestanti registrata con successo!');
    loadHaccpPests();
    loadHaccpAlerts();
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Errore durante il salvataggio.', 'error');
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function openPestInspectionDetail(inspectionId) {
  try {
    const res = await authFetch(`/api/haccp/pests/${inspectionId}`);
    if (!res.ok) throw new Error('Impossibile caricare il dettaglio dell\'ispezione.');
    const data = await res.json();
    const insp = data.inspection;

    document.getElementById('pest-modal-subtitle').textContent = `Controllo del ${insp.data_controllo} ore ${insp.ora_controllo || '--'} • Operatore: ${insp.operatore} • Prossima scadenza: ${insp.prossima_scadenza}`;

    const badgeBox = document.getElementById('pest-modal-status-badge');
    badgeBox.innerHTML = insp.has_presenze
      ? `<div class="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-900 font-bold flex items-center space-x-2"><i data-lucide="alert-triangle" class="w-4 h-4 text-rose-600"></i><span>Durante questo controllo sono state riscontrate tracce o presenze di infestanti. Verificare le azioni intraprese.</span></div>`
      : `<div class="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-900 font-bold flex items-center space-x-2"><i data-lucide="check-circle" class="w-4 h-4 text-emerald-600"></i><span>Ispezione conforme: assenza totale di infestanti riscontrata in tutte le 8 voci obbligatorie.</span></div>`;

    const notesBox = document.getElementById('pest-modal-notes-box');
    notesBox.innerHTML = `<strong>Note generali:</strong> ${escapeHtml(insp.note_generali || 'Nessuna nota aggiuntiva registrata.')}`;

    const tbody = document.getElementById('pest-modal-items-body');
    tbody.innerHTML = '';

    (insp.risposte || []).forEach(r => {
      const tr = document.createElement('tr');
      const isOk = r.esito === 'ASSENZA';
      const badge = isOk
        ? `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">Assenza</span>`
        : `<span class="px-2 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800">⚠️ Presenza</span>`;

      tr.innerHTML = `
        <td class="py-2.5 px-3 font-bold text-slate-900">${r.numero ? `${r.numero}. ` : ''}${escapeHtml(r.voce)}</td>
        <td class="py-2.5 px-3 text-center">${badge}</td>
        <td class="py-2.5 px-3 text-slate-700">${escapeHtml(r.zona || '--')}</td>
        <td class="py-2.5 px-3 text-slate-700 text-xs">
          ${r.azione ? `<strong>Azione:</strong> ${escapeHtml(r.azione)}<br>` : ''}
          ${r.note ? `<em>Note: ${escapeHtml(r.note)}</em>` : (!r.azione ? '--' : '')}
        </td>
      `;
      tbody.appendChild(tr);
    });

    openModal('modal-pest-detail');
    lucide.createIcons();
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Errore caricamento dettagli.', 'error');
  }
}

// ==========================================
// 8.3 HACCP: BANNER DEGLI AVVISI SCADUTI
// ==========================================
async function loadHaccpAlerts() {
  if (!activeVenueId || activeSection !== 'haccp') return;

  // Mostra il pulsante di Reset Rapido solo se l'utente corrente è amministratore
  const adminResetContainer = document.getElementById('haccp-admin-reset-container');
  if (adminResetContainer) {
    if (currentUser && currentUser.is_admin) {
      adminResetContainer.classList.remove('hidden');
    } else {
      adminResetContainer.classList.add('hidden');
    }
  }

  try {
    const res = await authFetch(`/api/haccp/alerts?sede_id=${activeVenueId}`);
    if (!res.ok) return;
    const data = await res.json();
    currentHaccpAlerts = data.alerts || [];

    const bannerContainer = document.getElementById('haccp-alerts-banner');
    if (!bannerContainer) return;

    if (currentHaccpAlerts.length === 0) {
      bannerContainer.classList.add('hidden');
      bannerContainer.innerHTML = '';
    } else {
      bannerContainer.classList.remove('hidden');
      bannerContainer.innerHTML = `
        <div class="p-4 rounded-2xl border-2 border-rose-500 bg-rose-50 text-rose-950 alert-banner-pulse shadow-md transition-all">
          <div class="flex items-center justify-between pb-2 border-b border-rose-200/80 mb-3">
            <div class="flex items-center space-x-2">
              <i data-lucide="alert-octagon" class="w-5 h-5 text-rose-600 animate-bounce"></i>
              <h4 class="font-black text-sm text-rose-900 uppercase tracking-wider">
                Attenzione: ${currentHaccpAlerts.length} ${currentHaccpAlerts.length === 1 ? 'attività o controllo scaduto' : 'attività o controlli scaduti'}
              </h4>
            </div>
            <span class="text-xs font-bold text-rose-700 bg-rose-100 px-2.5 py-0.5 rounded-full">
              Tocca un avviso per andare alla registrazione
            </span>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
            ${currentHaccpAlerts.map(a => `
              <div onclick="handleAlertBannerClick('${escapeHtml(a.tab)}', ${a.target_id || 'null'})"
                class="p-3 bg-white/90 hover:bg-white rounded-xl border border-rose-300 hover:border-rose-500 shadow-xs cursor-pointer transition-all flex items-start space-x-3 active:scale-[0.98]">
                <div class="w-7 h-7 rounded-lg bg-rose-100 text-rose-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <i data-lucide="bell-ring" class="w-4 h-4"></i>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between gap-1">
                    <strong class="text-xs font-black text-slate-900 truncate">${escapeHtml(a.nome_attrezzatura || a.titolo)}</strong>
                    <span class="text-[10px] font-bold text-rose-700 uppercase bg-rose-100/70 px-1.5 py-0.5 rounded flex-shrink-0">
                      ${escapeHtml(a.overdue_text)}
                    </span>
                  </div>
                  <p class="text-[11px] text-slate-600 mt-0.5 leading-snug">
                    ${a.is_first_time ? 'Nessun controllo precedente inserito' : `Ultimo controllo: <span class="font-mono font-semibold">${formatDisplayDateTime(a.ultima_registrazione)}</span>`}
                  </p>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    renderTabSpecificAlerts();
    lucide.createIcons();
  } catch (err) {
    console.error('Errore avvisi HACCP:', err);
  }
}

function handleAlertBannerClick(tabTarget, targetId) {
  switchHaccpTab(tabTarget);
  if (tabTarget === 'temp' && targetId) {
    setTimeout(() => {
      quickSelectFridgeForTemp(targetId);
    }, 150);
  } else if (tabTarget === 'oil' && targetId) {
    setTimeout(() => {
      const fry = cachedFryers ? cachedFryers.find(f => f.id === targetId) : null;
      if (fry) openRecordOilModal(fry.id, fry.nome_friggitrice || fry.nome);
      else openRecordOilModal(targetId, `Friggitrice ${targetId}`);
    }, 200);
  } else if (tabTarget === 'hood') {
    setTimeout(() => {
      if (typeof openRecordHoodModal === 'function') openRecordHoodModal();
    }, 150);
  } else if (tabTarget === 'cleaning_walls') {
    setTimeout(() => { openRecordCleaningModal('muri'); }, 150);
  } else if (tabTarget === 'cleaning_windows') {
    setTimeout(() => { openRecordCleaningModal('vetri'); }, 150);
  } else if (tabTarget === 'cleaning_warehouse') {
    setTimeout(() => { openRecordCleaningModal('magazzino'); }, 150);
  } else if (tabTarget === 'pests') {
    setTimeout(() => { startNewPestInspection(); }, 150);
  }
}

function renderTabSpecificAlerts() {
  const tabsToCheck = [
    { tab: 'temp', elId: 'tab-alert-temp' },
    { tab: 'oil', elId: 'tab-alert-oil' },
    { tab: 'hood', elId: 'tab-alert-hood' },
    { tab: 'cleaning_walls', elId: 'tab-alert-cleaning_walls' },
    { tab: 'cleaning_windows', elId: 'tab-alert-cleaning_windows' },
    { tab: 'cleaning_warehouse', elId: 'tab-alert-cleaning_warehouse' },
    { tab: 'pests', elId: 'tab-alert-pests' }
  ];

  tabsToCheck.forEach(item => {
    const el = document.getElementById(item.elId);
    if (!el) return;

    const matchingAlerts = currentHaccpAlerts.filter(a => a.tab === item.tab);
    if (matchingAlerts.length === 0) {
      el.classList.add('hidden');
      el.innerHTML = '';
    } else {
      el.classList.remove('hidden');
      el.innerHTML = `
        <div class="p-3.5 bg-rose-50 border-2 border-rose-500 rounded-2xl text-rose-950 alert-banner-pulse flex items-center justify-between gap-3 text-xs mb-4">
          <div class="flex items-center space-x-2">
            <i data-lucide="alert-triangle" class="w-5 h-5 text-rose-600 flex-shrink-0"></i>
            <div>
              <strong class="font-black text-rose-900 block">${matchingAlerts.length === 1 ? 'Attenzione: controllo scaduto per questa scheda' : `Attenzione: ${matchingAlerts.length} controlli scaduti per questa scheda`}</strong>
              <span class="text-rose-800">${matchingAlerts.map(a => `${a.nome_attrezzatura}: ${a.overdue_text}`).join(' • ')}</span>
            </div>
          </div>
          <span class="text-[11px] font-bold text-rose-700 bg-rose-100 px-2 py-1 rounded-lg flex-shrink-0">Registrazione richiesta</span>
        </div>
      `;
    }
  });

  lucide.createIcons();
}

/**
 * Reset rapido di tutti i controlli HACCP scaduti (Riservato Admin)
 * Inserisce registrazioni conformi per cappa, frighi, friggitrici, pulizie e infestanti,
 * azzerando all'istante tutti gli avvisi di scadenza e portando tutte le sezioni su 'IN REGOLA'.
 */
/**
 * Apre la modale di conferma Reset Rapido HACCP (Riservato Admin)
 */
function handleAdminResetHaccp() {
  if (!currentUser || !currentUser.is_admin) {
    showToast("Azione riservata all'amministratore.", "error");
    return;
  }

  const vId = activeVenueId || (currentVenues && currentVenues[0] ? currentVenues[0].id : 1);
  const venueObj = (currentVenues && currentVenues.find(v => v.id === vId));
  const venueName = venueObj ? venueObj.nome : 'questo locale';

  const titleEl = document.getElementById('reset-modal-venue-name');
  if (titleEl) titleEl.textContent = venueName;

  const chkBoth = document.getElementById('chk-reset-both-venues');
  if (chkBoth) chkBoth.checked = false;

  openModal('modal-confirm-admin-reset');
}

/**
 * Esegue il reset effettivo inviando la richiesta all'API
 */
async function executeAdminResetHaccp() {
  if (!currentUser || !currentUser.is_admin) {
    showToast("Azione riservata all'amministratore.", "error");
    return;
  }

  const vId = activeVenueId || (currentVenues && currentVenues[0] ? currentVenues[0].id : 1);
  const chkBoth = document.getElementById('chk-reset-both-venues');
  const resetBoth = chkBoth ? chkBoth.checked : false;

  const btn = document.getElementById('btn-modal-confirm-reset-action');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Registrazione in corso...</span>`;
    if (typeof lucide !== 'undefined' && lucide.createIcons) lucide.createIcons();
  }

  try {
    const res = await authFetch('/api/haccp/admin-reset-alerts', {
      method: 'POST',
      body: JSON.stringify({ sede_id: vId, both_sedi: resetBoth })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Errore durante il reset dei controlli.');
    }
    const data = await res.json();
    closeModal('modal-confirm-admin-reset');
    showToast(data.message || 'Tutti i controlli sono stati registrati come eseguiti e conformi!', 'success');

    // Ricarica subito gli avvisi (che diventeranno 0, nascondendo i banner rossi)
    await loadHaccpAlerts();

    // Ricarica i dati della scheda HACCP attualmente aperta
    if (currentHaccpTab === 'temp' && typeof loadHaccpTemperature === 'function') {
      await loadHaccpTemperature();
    } else if (currentHaccpTab === 'oil' && typeof loadHaccpOil === 'function') {
      await loadHaccpOil();
    } else if (currentHaccpTab === 'hood' && typeof loadHaccpHood === 'function') {
      await loadHaccpHood();
    } else if (currentHaccpTab === 'cleaning_walls' && typeof loadHaccpCleaning === 'function') {
      await loadHaccpCleaning('muri');
    } else if (currentHaccpTab === 'cleaning_windows' && typeof loadHaccpCleaning === 'function') {
      await loadHaccpCleaning('vetri');
    } else if (currentHaccpTab === 'cleaning_warehouse' && typeof loadHaccpCleaning === 'function') {
      await loadHaccpCleaning('magazzino');
    } else if (currentHaccpTab === 'pests' && typeof loadHaccpPests === 'function') {
      await loadHaccpPests();
    }

    if (typeof lucide !== 'undefined' && lucide.createIcons) {
      lucide.createIcons();
    }
  } catch (err) {
    console.error('Errore reset admin HACCP:', err);
    showToast(err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="check-check" class="w-4 h-4"></i><span>Sì, Registra Tutto Conforme</span>`;
      if (typeof lucide !== 'undefined' && lucide.createIcons) lucide.createIcons();
    }
  }
}

// ==========================================
// 9. GESTIONE UTENTI & PERMESSI (ADMIN)
// ==========================================
async function openUsersManagementModal() {
  if (!currentUser || !currentUser.is_admin) {
    showToast('Pannello riservato all\'amministratore.', 'error');
    return;
  }

  openModal('modal-manage-users');
  closeUserEditor();

  try {
    const [catRes, uRes] = await Promise.all([
      authFetch('/api/users/permissions-catalog'),
      authFetch('/api/users')
    ]);
    const catData = await catRes.json();
    const uData = await uRes.json();

    cachedPermissionsCatalog = catData.catalog || [];
    cachedUsers = uData.users || [];

    renderUsersTable();
  } catch (err) {
    console.error('Errore gestione utenti:', err);
  }
}

function renderUsersTable() {
  const tbody = document.getElementById('users-table-body');
  tbody.innerHTML = '';

  cachedUsers.forEach(u => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-50 transition-colors';

    // Badge Sedi
    let sediHtml = '';
    if (u.is_admin) {
      sediHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-800">Tutti i locali (Admin)</span>`;
    } else if (u.authorized_sedi && u.authorized_sedi.length > 0) {
      u.authorized_sedi.forEach(sid => {
        if (sid === 1) sediHtml += `<span class="px-2 py-0.5 rounded text-[10px] font-bold badge-krugel mr-1">Krügel</span>`;
        if (sid === 2) sediHtml += `<span class="px-2 py-0.5 rounded text-[10px] font-bold badge-incontro mr-1">L’Incontro</span>`;
      });
    } else {
      sediHtml = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold text-slate-400">Nessuna sede</span>`;
    }

    const statusBadge = u.is_active
      ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">Attivo</span>`
      : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">Disattivato</span>`;

    tr.innerHTML = `
      <td class="py-2.5 px-3 font-mono font-bold text-slate-900">${u.username}</td>
      <td class="py-2.5 px-3 font-semibold text-slate-800">${u.full_name}</td>
      <td class="py-2.5 px-3">
        ${u.is_admin ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-800">Amministratore</span>' : '<span class="text-slate-600">Standard</span>'}
      </td>
      <td class="py-2.5 px-3">${sediHtml}</td>
      <td class="py-2.5 px-3 text-center">${statusBadge}</td>
      <td class="py-2.5 px-3 text-right">
        <div class="inline-flex space-x-1">
          <button onclick="openEditUserForm(${u.id})" class="px-2 py-1 rounded text-xs font-semibold text-indigo-600 hover:bg-indigo-50 border border-indigo-200">
            Modifica
          </button>
          ${u.username !== 'admin' ? `
            <button onclick="toggleUserActive(${u.id}, ${u.is_active})" class="px-2 py-1 rounded text-xs font-semibold ${u.is_active ? 'text-rose-600 hover:bg-rose-50 border border-rose-200' : 'text-emerald-600 hover:bg-emerald-50 border border-emerald-200'}">
              ${u.is_active ? 'Disattiva' : 'Attiva'}
            </button>
          ` : ''}
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function openCreateUserForm() {
  document.getElementById('user-editor-container').classList.remove('hidden');
  document.getElementById('user-editor-title').textContent = 'Crea Nuovo Account Utente';
  document.getElementById('edit-user-id').value = '';
  document.getElementById('form-user-username').value = '';
  document.getElementById('form-user-username').disabled = false;
  document.getElementById('form-user-fullname').value = '';
  document.getElementById('form-user-password').value = '';
  document.getElementById('form-user-password').required = true;
  document.getElementById('form-user-password').placeholder = 'Minimo 4 caratteri';
  document.getElementById('form-user-isadmin').checked = false;
  document.getElementById('form-user-isactive').checked = true;

  renderPermissionsMatrix({});
}

function openEditUserForm(userId) {
  const user = cachedUsers.find(u => u.id === userId);
  if (!user) return;

  document.getElementById('user-editor-container').classList.remove('hidden');
  document.getElementById('user-editor-title').textContent = `Modifica Account: ${user.username}`;
  document.getElementById('edit-user-id').value = user.id;
  document.getElementById('form-user-username').value = user.username;
  document.getElementById('form-user-username').disabled = true; // Non modificare username
  document.getElementById('form-user-fullname').value = user.full_name;
  document.getElementById('form-user-password').value = '';
  document.getElementById('form-user-password').required = false;
  document.getElementById('form-user-password').placeholder = 'Lascia vuoto per non modificare la password';
  document.getElementById('form-user-isadmin').checked = user.is_admin;
  document.getElementById('form-user-isactive').checked = user.is_active;

  // Mappa permessi esistenti: { sede_id: [permCode1, permCode2] }
  const assigned = {};
  if (user.permissions) {
    user.permissions.forEach(p => {
      if (!assigned[p.sede_id]) assigned[p.sede_id] = [];
      assigned[p.sede_id].push(p.permesso);
    });
  }

  renderPermissionsMatrix(assigned);
  toggleAdminCheckboxInEditor(document.getElementById('form-user-isadmin'));
}

function closeUserEditor() {
  document.getElementById('user-editor-container').classList.add('hidden');
}

function toggleAdminCheckboxInEditor(checkbox) {
  const matrix = document.getElementById('permissions-matrix-container');
  if (checkbox.checked) {
    matrix.classList.add('opacity-40', 'pointer-events-none');
  } else {
    matrix.classList.remove('opacity-40', 'pointer-events-none');
  }
}

function renderPermissionsMatrix(assignedMap = {}) {
  const container = document.getElementById('permissions-matrix-venues');
  container.innerHTML = '';

  const sedi = [
    { id: 1, name: 'Krügel – Lavis', badgeClass: 'badge-krugel' },
    { id: 2, name: 'Cafè L’Incontro – Pergine', badgeClass: 'badge-incontro' }
  ];

  sedi.forEach(s => {
    const venueCard = document.createElement('div');
    venueCard.className = 'p-4 rounded-xl border border-slate-200 bg-white space-y-3';

    let sectionsHtml = '';
    cachedPermissionsCatalog.forEach(cat => {
      let permsCheckboxes = '';
      cat.permissions.forEach(p => {
        const isChecked = assignedMap[s.id] && assignedMap[s.id].includes(p.code);
        permsCheckboxes += `
          <label class="flex items-center space-x-2 text-xs cursor-pointer hover:bg-slate-50 p-1 rounded">
            <input type="checkbox" data-sede="${s.id}" data-perm="${p.code}" ${isChecked ? 'checked' : ''}
              class="perm-checkbox rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5">
            <span class="text-slate-700">${p.label}</span>
          </label>
        `;
      });

      sectionsHtml += `
        <div class="border-t border-slate-100 pt-2">
          <span class="font-bold text-[11px] uppercase tracking-wider text-slate-500 block mb-1">${cat.section}</span>
          <div class="space-y-1 pl-1">
            ${permsCheckboxes}
          </div>
        </div>
      `;
    });

    venueCard.innerHTML = `
      <div class="flex items-center justify-between pb-2 border-b border-slate-200">
        <span class="font-bold text-xs ${s.badgeClass} px-2 py-0.5 rounded">${s.name}</span>
        <div class="space-x-1">
          <button type="button" onclick="selectAllPermsForVenue(${s.id}, true)" class="text-[10px] text-indigo-600 hover:underline font-semibold">Tutti</button>
          <span class="text-slate-300">&bull;</span>
          <button type="button" onclick="selectAllPermsForVenue(${s.id}, false)" class="text-[10px] text-slate-500 hover:underline">Nessuno</button>
        </div>
      </div>
      <div class="space-y-2">
        ${sectionsHtml}
      </div>
    `;

    container.appendChild(venueCard);
  });
}

function selectAllPermsForVenue(sedeId, checkState) {
  const checkboxes = document.querySelectorAll(`input[data-sede="${sedeId}"]`);
  checkboxes.forEach(cb => cb.checked = checkState);
}

async function handleSaveUserSubmit(event) {
  event.preventDefault();
  const editId = document.getElementById('edit-user-id').value;
  const username = document.getElementById('form-user-username').value.trim();
  const fullName = document.getElementById('form-user-fullname').value.trim();
  const password = document.getElementById('form-user-password').value;
  const isAdmin = document.getElementById('form-user-isadmin').checked;
  const isActive = document.getElementById('form-user-isactive').checked;

  // Raccogli permessi selezionati
  const permissions = [];
  if (!isAdmin) {
    const checkboxes = document.querySelectorAll('.perm-checkbox:checked');
    checkboxes.forEach(cb => {
      permissions.push({
        sede_id: parseInt(cb.dataset.sede),
        permesso: cb.dataset.perm
      });
    });
  }

  const payload = {
    username: username,
    full_name: fullName,
    is_admin: isAdmin,
    is_active: isActive,
    permissions: permissions
  };
  if (password) payload.password = password;

  try {
    let res;
    if (editId) {
      res = await authFetch(`/api/users/${editId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } else {
      res = await authFetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    }

    const data = await res.json();
    showToast(data.message);
    closeUserEditor();

    // Ricarica lista utenti
    const uRes = await authFetch('/api/users');
    const uData = await uRes.json();
    cachedUsers = uData.users || [];
    renderUsersTable();
  } catch (err) {
    console.error(err);
  }
}

async function toggleUserActive(userId, currentActive) {
  const actionText = currentActive ? 'disattivare' : 'riattivare';
  if (!confirm(`Sei sicuro di voler ${actionText} questo account? Tutte le sessioni attive verranno immediatamente revocate.`)) return;

  try {
    const res = await authFetch(`/api/users/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !currentActive })
    });
    const data = await res.json();
    showToast(data.message);

    const uRes = await authFetch('/api/users');
    const uData = await uRes.json();
    cachedUsers = uData.users || [];
    renderUsersTable();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// 10. FATTURE & PREZZI (ESISTENTI PRESERVATE)
// ==========================================
async function loadAnalytics() {
  const months = document.getElementById('analytics-months').value || 6;
  const search = document.getElementById('analytics-search').value.trim();
  const categoria = document.getElementById('analytics-category-filter').value;

  let url = `/api/analytics/purchases?months=${months}`;
  if (activeVenueId) url += `&sede_id=${activeVenueId}`;
  if (categoria) url += `&categoria=${encodeURIComponent(categoria)}`;
  if (search) url += `&fornitore=${encodeURIComponent(search)}`;

  try {
    const [kpiRes, dataRes] = await Promise.all([
      authFetch(`/api/analytics/summary?months=${months}${activeVenueId ? `&sede_id=${activeVenueId}` : ''}`),
      authFetch(url)
    ]);

    const kpiData = await kpiRes.json();
    const tableData = await dataRes.json();

    document.getElementById('kpi-total-spend').textContent = formatCurrency(kpiData.kpi.spesa_netta_totale);
    document.getElementById('kpi-mapped-products').textContent = kpiData.kpi.prodotti_mappati;

    let krugelSpend = 0;
    let incontroSpend = 0;
    let krugelCount = 0;
    let incontroCount = 0;
    kpiData.spesa_sedi.forEach(s => {
      if (s.id === 1) {
        krugelSpend = s.spesa_sede || 0;
        krugelCount = s.num_fatture || 0;
      }
      if (s.id === 2) {
        incontroSpend = s.spesa_sede || 0;
        incontroCount = s.num_fatture || 0;
      }
    });

    document.getElementById('kpi-spend-krugel').textContent = formatCurrency(krugelSpend);
    document.getElementById('kpi-krugel-sub').textContent = `${krugelCount} fatture`;
    document.getElementById('kpi-spend-incontro').textContent = formatCurrency(incontroSpend);
    document.getElementById('kpi-incontro-sub').textContent = `${incontroCount} fatture`;

    loadCategoriesFilter();
    renderAnalyticsTable(tableData.items, search);
    updateUnassignedBadge();
  } catch (err) {
    console.error('Errore analisi acquisti:', err);
  }
}

async function loadCategoriesFilter() {
  const sel = document.getElementById('analytics-category-filter');
  if (sel.children.length > 1) return;

  try {
    const res = await authFetch('/api/analytics/categories');
    const d = await res.json();
    d.categories.forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = cat;
      sel.appendChild(opt);
    });
  } catch (err) {
    console.error(err);
  }
}

function renderAnalyticsTable(items, searchTerm = '') {
  const tbody = document.getElementById('analytics-table-body');
  tbody.innerHTML = '';

  let filtered = items;
  if (searchTerm) {
    const st = searchTerm.toLowerCase();
    filtered = items.filter(it =>
      it.prodotto_nome.toLowerCase().includes(st) ||
      it.fornitore.toLowerCase().includes(st) ||
      it.categoria.toLowerCase().includes(st)
    );
  }

  if (!filtered || filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="py-12 text-center text-slate-400">
          <div class="flex flex-col items-center justify-center space-y-2">
            <i data-lucide="package-search" class="w-8 h-8 text-slate-300"></i>
            <span class="text-sm font-medium">Nessun acquisto trovato per il periodo e i filtri selezionati.</span>
          </div>
        </td>
      </tr>
    `;
    lucide.createIcons();
    return;
  }

  let unmappedCount = 0;

  filtered.forEach(it => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-indigo-50/40 transition-colors cursor-pointer group';
    tr.onclick = () => openDrilldown(it);

    if (!it.is_mapped) unmappedCount++;

    let sediBadges = '';
    it.sedi.forEach(s => {
      if (s === 'Krügel') sediBadges += `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-krugel mr-1">Krügel</span>`;
      else if (s === 'Cafè L’Incontro') sediBadges += `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-incontro mr-1">L’Incontro</span>`;
      else sediBadges += `<span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 mr-1">${s}</span>`;
    });

    let deltaBadge = `<span class="text-slate-400 text-xs">0%</span>`;
    if (it.variazione_perc > 0) {
      const color = it.variazione_perc > 10 ? 'text-amber-600 bg-amber-50' : 'text-slate-600 bg-slate-50';
      deltaBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-bold ${color}">+${it.variazione_perc}%</span>`;
    }

    const isUnmapped = !it.is_mapped;
    const cleanDesc = (it.prodotto_nome || '').replace('[Da Mappare] ', '').replace(/'/g, "\\'");
    const prodDisplay = isUnmapped
      ? `<div class="flex items-center space-x-1.5">
           <button onclick="event.stopPropagation(); openProductMappingModal({id: null, descrizione: '${cleanDesc}'})" title="Clicca qui per associare questo prodotto" class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300 hover:bg-amber-200 transition-colors shadow-xs">
             ⚠️ Da mappare
           </button>
           <span class="font-medium text-slate-800 truncate max-w-xs">${it.prodotto_nome.replace('[Da Mappare] ', '')}</span>
         </div>`
      : `<div><strong class="font-bold text-slate-900 block group-hover:text-indigo-600 transition-colors">${it.prodotto_nome}</strong><span class="text-[11px] text-slate-500">${it.categoria}</span></div>`;

    tr.innerHTML = `
      <td class="py-3 px-4">${prodDisplay}</td>
      <td class="py-3 px-4">
        <span class="font-medium text-slate-800 block">${it.fornitore}</span>
        <span class="text-[11px] text-slate-400">P.IVA: ${it.fornitore_piva || 'N.D.'}</span>
      </td>
      <td class="py-3 px-4">${sediBadges}</td>
      <td class="py-3 px-4 text-right">
        <span class="font-semibold text-slate-900">${formatQty(it.quantita_fatturata)}</span>
        <span class="text-xs font-bold text-indigo-700 ml-1">${it.unita_base}</span>
        <span class="block text-[10px] text-slate-400">${it.confezione_desc}</span>
      </td>
      <td class="py-3 px-4 text-right text-slate-600 font-mono">${formatCurrency(it.prezzo_min)} / ${it.unita_base}</td>
      <td class="py-3 px-4 text-right font-mono bg-indigo-50/40 text-indigo-900 font-black text-sm">
        ${formatCurrency(it.prezzo_medio_ponderato)} <span class="text-[10px] font-normal text-indigo-600">/ ${it.unita_base}</span>
      </td>
      <td class="py-3 px-4 text-right text-slate-600 font-mono">${formatCurrency(it.prezzo_max)} / ${it.unita_base}</td>
      <td class="py-3 px-4 text-right">${deltaBadge}</td>
      <td class="py-3 px-4 text-center">
        <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 group-hover:bg-indigo-100 group-hover:text-indigo-800">
          ${it.num_fatture} doc <i data-lucide="chevron-right" class="w-3 h-3 ml-0.5"></i>
        </span>
      </td>
    `;
    tbody.appendChild(tr);
  });

  const unmappedEl = document.getElementById('kpi-unmapped-alert');
  if (unmappedEl) {
    unmappedEl.textContent = `${unmappedCount} righe da associare a prodotti`;
    if (unmappedCount > 0) unmappedEl.className = 'text-xs text-amber-600 mt-1 font-bold';
    else unmappedEl.className = 'text-xs text-slate-400 mt-1';
  }

  lucide.createIcons();
}

// Drilldown Tracciabilità Righe Prezzo
async function openDrilldown(item) {
  currentDrilldownContext = item;
  document.getElementById('drilldown-title').textContent = item.prodotto_nome;
  document.getElementById('drilldown-category').textContent = item.categoria;
  document.getElementById('drilldown-subtitle').textContent = `Fornitore: ${item.fornitore} (P.IVA ${item.fornitore_piva || 'N.D.'}) • Unità base: ${item.unita_base}`;

  if (!item.is_mapped) {
    document.getElementById('drilldown-banner-text').innerHTML = `
      <span class="font-bold text-amber-900">⚠️ Prodotto non ancora associato:</span>
      <span class="text-indigo-900 ml-1">clicca su "Associa Prodotto Ora" per normalizzare l'unità di misura e confrontare i prezzi.</span>
    `;
    const btnMap = document.querySelector('#drilldown-conversion-banner button');
    if (btnMap) btnMap.textContent = 'Associa Prodotto Ora';
  } else {
    document.getElementById('drilldown-banner-text').textContent = `Fattore di conversione confezione: ${item.confezione_desc} • Prezzo Medio Ponderato: ${formatCurrency(item.prezzo_medio_ponderato)} / ${item.unita_base}`;
    const btnMap = document.querySelector('#drilldown-conversion-banner button');
    if (btnMap) btnMap.textContent = 'Modifica Conversione';
  }

  const months = document.getElementById('analytics-months').value || 6;
  let url = `/api/analytics/drilldown?months=${months}&fornitore=${encodeURIComponent(item.fornitore)}`;
  if (item.prodotto_id) url += `&prodotto_id=${item.prodotto_id}`;
  else url += `&raw_description=${encodeURIComponent(item.prodotto_nome.replace('[Da Mappare] ', ''))}`;
  if (activeVenueId) url += `&sede_id=${activeVenueId}`;

  const tbody = document.getElementById('drilldown-table-body');
  tbody.innerHTML = `<tr><td colspan="10" class="py-8 text-center text-slate-400">Caricamento tracciabilità righe...</td></tr>`;
  openModal('modal-drilldown');

  try {
    const res = await authFetch(url);
    const d = await res.json();
    tbody.innerHTML = '';

    if (!d.lines || d.lines.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="py-8 text-center text-slate-400">Nessuna riga di fattura trovata.</td></tr>`;
      return;
    }

    d.lines.forEach(l => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition-colors';

      let venueBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-unassigned">Non assegnata</span>`;
      if (l.sede_nome === 'Krügel') venueBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-krugel">Krügel</span>`;
      else if (l.sede_nome === 'Cafè L’Incontro') venueBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-incontro">Cafè L’Incontro</span>`;

      let ncBadge = '';
      if (l.is_credit_note) {
        ncBadge = `<span class="ml-1 px-1.5 py-0.2 rounded text-[9px] font-bold badge-nc">NC (Storno)</span>`;
      }

      let scontoStr = '-';
      if (l.sconto_percentuale > 0) scontoStr = `-${l.sconto_percentuale}%`;
      else if (l.sconto_importo > 0) scontoStr = `-${formatCurrency(l.sconto_importo)}`;

      tr.innerHTML = `
        <td class="py-2.5 px-3">
          <span class="font-bold text-slate-800 block">${l.numero_documento} ${ncBadge}</span>
          <span class="text-[10px] text-slate-500">${l.data_documento}</span>
        </td>
        <td class="py-2.5 px-3">${venueBadge}</td>
        <td class="py-2.5 px-3 font-mono text-slate-600">${l.riferimento_ddt_numero ? `${l.riferimento_ddt_numero} (${l.riferimento_ddt_data || ''})` : '-'}</td>
        <td class="py-2.5 px-3">
          <span class="font-medium text-slate-900 block">${l.descrizione_originale}</span>
          <span class="text-[10px] text-slate-400 font-mono">Cod: ${l.codice_articolo || 'N.D.'} • Linea #${l.numero_linea}</span>
        </td>
        <td class="py-2.5 px-3 text-right font-medium text-slate-800">${formatQty(l.quantita_originale)} ${l.um_originale}</td>
        <td class="py-2.5 px-3 text-right text-slate-500">${formatCurrency(l.prezzo_unitario_lordo)}</td>
        <td class="py-2.5 px-3 text-right text-emerald-600 font-semibold">${scontoStr}</td>
        <td class="py-2.5 px-3 text-right font-medium text-slate-700">${formatCurrency(l.prezzo_unitario_netto)}</td>
        <td class="py-2.5 px-3 text-right font-bold text-indigo-900 bg-indigo-50/50">${formatQty(l.quantita_base)} ${l.prodotto_um_base}</td>
        <td class="py-2.5 px-3 text-right font-mono font-bold text-indigo-900 bg-indigo-50/50">${formatCurrency(l.prezzo_unitario_base)}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

function openMappingFromDrilldown() {
  if (!currentDrilldownContext) return;
  closeModal('modal-drilldown');
  openProductMappingModal({
    descrizione: currentDrilldownContext.prodotto_nome.replace('[Da Mappare] ', ''),
    id: null
  });
}

// Vista Fatture
async function loadInvoices() {
  const search = document.getElementById('invoices-search').value.trim();
  const stato = document.getElementById('invoices-status-filter').value;
  const tipo = document.getElementById('invoices-type-filter').value;

  let url = `/api/invoices?`;
  if (activeVenueId) url += `sede_id=${activeVenueId}&`;
  if (stato) url += `stato=${encodeURIComponent(stato)}&`;
  if (tipo) url += `tipo=${encodeURIComponent(tipo)}&`;
  if (search) url += `search=${encodeURIComponent(search)}&`;

  try {
    const res = await authFetch(url);
    const data = await res.json();

    document.getElementById('invoices-count-label').textContent = data.total;
    document.getElementById('nav-count-invoices').textContent = data.total;

    const tbody = document.getElementById('invoices-table-body');
    tbody.innerHTML = '';

    if (!data.invoices || data.invoices.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="py-12 text-center text-slate-400">
            <i data-lucide="inbox" class="w-8 h-8 text-slate-300 mx-auto mb-2"></i>
            <span>Nessuna fattura trovata per questo locale.</span>
          </td>
        </tr>
      `;
      lucide.createIcons();
      return;
    }

    data.invoices.forEach(inv => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition-colors cursor-pointer';
      tr.onclick = (e) => {
        if (!e.target.closest('button')) openInvoiceDetail(inv.id);
      };

      let sedeBadge = '';
      if (inv.sede_id === 1 || inv.sede_nome === 'Krügel') {
        sedeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold badge-krugel">Krügel</span>`;
      } else if (inv.sede_id === 2 || inv.sede_nome === 'Cafè L’Incontro') {
        sedeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold badge-incontro">Cafè L’Incontro</span>`;
      } else if (inv.stato_assegnazione === 'PARZIALE' || inv.metodo_assegnazione === 'AUTO_DDT') {
        sedeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold badge-mixed">Mista (DDT separati)</span>`;
      } else {
        sedeBadge = `<span class="px-2 py-0.5 rounded text-xs font-semibold badge-unassigned">Da Assegnare</span>`;
      }

      let tipoBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">${inv.tipo_documento}</span>`;
      if (inv.tipo_documento === 'TD04') {
        tipoBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-bold badge-nc">TD04 (Nota Credito)</span>`;
      } else if (inv.tipo_documento === 'TD24') {
        tipoBadge = `<span class="px-2 py-0.5 rounded text-[11px] font-medium bg-blue-50 text-blue-700">TD24 (Differita)</span>`;
      }

      const isNC = inv.tipo_documento === 'TD04';
      const totalDisplay = isNC ? `-${formatCurrency(inv.importo_totale)}` : formatCurrency(inv.importo_totale);
      const netDisplay = isNC ? `-${formatCurrency(inv.imponibile_totale)}` : formatCurrency(inv.imponibile_totale);

      tr.innerHTML = `
        <td class="py-3 px-4">
          <strong class="font-bold text-slate-900 block text-sm">${inv.numero_documento}</strong>
          <span class="text-xs text-slate-500">${inv.data_documento}</span>
        </td>
        <td class="py-3 px-4">${tipoBadge}</td>
        <td class="py-3 px-4">
          <span class="font-semibold text-slate-800 block">${inv.cedente_denominazione}</span>
          <span class="text-xs text-slate-400">P.IVA: ${inv.cedente_piva || 'N.D.'}</span>
        </td>
        <td class="py-3 px-4">${sedeBadge}</td>
        <td class="py-3 px-4 max-w-xs truncate text-xs text-slate-600" title="${inv.indirizzo_resa_estratto || ''}">
          ${inv.indirizzo_resa_estratto || '<span class="text-slate-400 italic">Non presente nel file</span>'}
        </td>
        <td class="py-3 px-4 text-right font-mono text-slate-600 text-xs">${netDisplay}</td>
        <td class="py-3 px-4 text-right font-mono font-bold text-slate-900 ${isNC ? 'text-purple-700' : ''}">${totalDisplay}</td>
        <td class="py-3 px-4 text-center">
          <span class="px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-700 font-semibold">${inv.tot_righe}</span>
        </td>
        <td class="py-3 px-4 text-center">
          <button onclick="openInvoiceDetail(${inv.id})" class="p-1.5 rounded-lg text-slate-500 hover:text-indigo-600 hover:bg-indigo-50">
            <i data-lucide="eye" class="w-4 h-4"></i>
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    lucide.createIcons();
  } catch (err) {
    console.error(err);
  }
}

async function openInvoiceDetail(invoiceId) {
  currentDetailInvoiceId = invoiceId;
  openModal('modal-invoice-detail');
  const tbody = document.getElementById('inv-modal-lines-body');
  tbody.innerHTML = `<tr><td colspan="10" class="py-8 text-center text-slate-400">Caricamento dettagli fattura...</td></tr>`;

  try {
    const res = await authFetch(`/api/invoices/${invoiceId}`);
    const doc = await res.json();

    document.getElementById('inv-modal-title').textContent = `Fattura N. ${doc.numero_documento}`;
    document.getElementById('inv-modal-supplier').textContent = `Cedente: ${doc.cedente_denominazione} • P.IVA: ${doc.cedente_piva || doc.cedente_codice_fiscale}`;
    document.getElementById('inv-modal-date').textContent = doc.data_documento;
    document.getElementById('inv-modal-total').textContent = formatCurrency(doc.importo_totale);
    document.getElementById('inv-modal-net').textContent = formatCurrency(doc.imponibile_totale);
    document.getElementById('inv-modal-delivery').textContent = doc.indirizzo_resa_estratto || 'Nessun indirizzo resa esplicito';

    const tBadge = document.getElementById('inv-modal-type-badge');
    tBadge.textContent = doc.tipo_documento;
    if (doc.tipo_documento === 'TD04') tBadge.className = 'px-2 py-0.5 rounded text-xs font-bold badge-nc';
    else tBadge.className = 'px-2 py-0.5 rounded text-xs font-semibold bg-slate-200 text-slate-700';

    const vBadge = document.getElementById('inv-modal-venue-badge');
    if (doc.sede_nome === 'Krügel') {
      vBadge.textContent = 'Krügel (Via Nazionale)';
      vBadge.className = 'px-2 py-0.5 rounded text-xs font-semibold badge-krugel';
    } else if (doc.sede_nome === 'Cafè L’Incontro') {
      vBadge.textContent = 'Cafè L’Incontro (Via Tamarisi 2)';
      vBadge.className = 'px-2 py-0.5 rounded text-xs font-semibold badge-incontro';
    } else if (doc.stato_assegnazione === 'PARZIALE' || doc.metodo_assegnazione === 'AUTO_DDT') {
      vBadge.textContent = 'Mista (Krügel & L’Incontro per DDT)';
      vBadge.className = 'px-2 py-0.5 rounded text-xs font-semibold badge-mixed';
    } else {
      vBadge.textContent = 'Da Assegnare';
      vBadge.className = 'px-2 py-0.5 rounded text-xs font-semibold badge-unassigned';
    }

    tbody.innerHTML = '';
    doc.righe.forEach(r => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 transition-colors';

      let lineVenueBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-unassigned">Non assegnata</span>`;
      if (r.sede_nome === 'Krügel') lineVenueBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-krugel">Krügel</span>`;
      else if (r.sede_nome === 'Cafè L’Incontro') lineVenueBadge = `<span class="px-2 py-0.5 rounded text-[10px] font-semibold badge-incontro">L’Incontro</span>`;

      let prodTag = '';
      if (r.prodotto_nome) {
        prodTag = `<span class="font-semibold text-slate-800">${r.prodotto_nome}</span> <span class="text-[10px] text-slate-400">(${r.prodotto_um_base})</span>`;
      } else {
        prodTag = `<button onclick="openProductMappingModal({id: ${r.id}, descrizione: '${r.descrizione.replace(/'/g, "\\'")}'})" class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 hover:bg-amber-200">+ Associa Prodotto</button>`;
      }

      let scontoStr = '-';
      if (r.sconto_percentuale > 0) scontoStr = `-${r.sconto_percentuale}%`;
      else if (r.sconto_importo > 0) scontoStr = `-${formatCurrency(r.sconto_importo)}`;

      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono text-slate-400">${r.numero_linea}</td>
        <td class="py-2.5 px-3">
          <span class="font-medium text-slate-900 block">${r.descrizione}</span>
          <span class="text-[10px] text-slate-400 font-mono">Cod: ${r.codice_articolo || 'N.D.'}</span>
        </td>
        <td class="py-2.5 px-3 font-mono text-slate-600">${r.riferimento_ddt_numero ? `${r.riferimento_ddt_numero}` : '-'}</td>
        <td class="py-2.5 px-3">${lineVenueBadge}</td>
        <td class="py-2.5 px-3">${prodTag}</td>
        <td class="py-2.5 px-3 text-right font-medium">${formatQty(r.quantita)} ${r.unita_misura}</td>
        <td class="py-2.5 px-3 text-right text-slate-500">${formatCurrency(r.prezzo_unitario_lordo)}</td>
        <td class="py-2.5 px-3 text-right text-emerald-600 font-semibold">${scontoStr}</td>
        <td class="py-2.5 px-3 text-right font-medium text-slate-800">${formatCurrency(r.prezzo_unitario_netto)}</td>
        <td class="py-2.5 px-3 text-right font-mono font-bold text-slate-900">${formatCurrency(r.prezzo_totale_netto)}</td>
      `;
      tbody.appendChild(tr);
    });

    lucide.createIcons();
  } catch (err) {
    console.error(err);
  }
}

// Vista Da Assegnare
async function loadUnassigned() {
  selectedUnassignedLineIds.clear();

  try {
    const [sumRes, invRes, linesRes] = await Promise.all([
      authFetch('/api/unassigned/summary'),
      authFetch('/api/unassigned/invoices'),
      authFetch('/api/unassigned/lines')
    ]);

    const summary = await sumRes.json();
    const invoicesData = await invRes.json();
    const linesData = await linesRes.json();

    const totWaiting = summary.fatture_da_assegnare + summary.righe_da_assegnare;
    const navBadge = document.getElementById('nav-count-unassigned');
    if (totWaiting > 0) {
      navBadge.textContent = totWaiting;
      navBadge.classList.remove('hidden');
    } else {
      navBadge.classList.add('hidden');
    }

    document.getElementById('unassigned-invoices-badge').textContent = `${invoicesData.count} in sospeso`;

    const invList = document.getElementById('unassigned-invoices-list');
    invList.innerHTML = '';

    if (!invoicesData.invoices || invoicesData.invoices.length === 0) {
      invList.innerHTML = `<p class="p-8 text-center text-slate-400 text-sm">Nessuna fattura intera da assegnare. Tutte le fatture hanno una sede definita!</p>`;
    } else {
      invoicesData.invoices.forEach(inv => {
        const item = document.createElement('div');
        item.className = 'p-4 flex flex-wrap items-center justify-between gap-3 hover:bg-slate-50 transition-colors';
        item.innerHTML = `
          <div>
            <div class="flex items-center space-x-2">
              <span class="font-bold text-slate-900 text-sm">Fattura ${inv.numero_documento}</span>
              <span class="text-xs text-slate-400">del ${inv.data_documento}</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-bold badge-unassigned">${inv.stato_assegnazione}</span>
            </div>
            <p class="text-xs text-slate-600 mt-1">Fornitore: <strong>${inv.cedente_denominazione}</strong> • Importo: <strong>${formatCurrency(inv.importo_totale)}</strong> (${inv.tot_righe} righe)</p>
            <p class="text-xs text-amber-700 mt-0.5">Indirizzo rilevato: ${inv.indirizzo_resa_estratto || 'Nessun indirizzo resa specifico nel file XML'}</p>
          </div>
          <div class="flex items-center space-x-2">
            ${userHasPermission('fatture.assign') ? `
              <button onclick="quickAssignDoc(${inv.id}, 1)" class="px-3 py-1.5 text-xs font-bold rounded-lg text-amber-900 bg-amber-100 hover:bg-amber-200 border border-amber-300 transition-colors">
                🍺 Assegna a Krügel
              </button>
              <button onclick="quickAssignDoc(${inv.id}, 2)" class="px-3 py-1.5 text-xs font-bold rounded-lg text-emerald-900 bg-emerald-100 hover:bg-emerald-200 border border-emerald-300 transition-colors">
                ☕ Assegna a Cafè L’Incontro
              </button>
            ` : ''}
            <button onclick="openInvoiceDetail(${inv.id})" class="px-2.5 py-1.5 text-xs rounded-lg text-slate-600 hover:bg-slate-200 border border-slate-300">
              Dettaglio
            </button>
          </div>
        `;
        invList.appendChild(item);
      });
    }

    const tbodyLines = document.getElementById('unassigned-lines-table-body');
    tbodyLines.innerHTML = '';

    if (!linesData.lines || linesData.lines.length === 0) {
      tbodyLines.innerHTML = `<tr><td colspan="8" class="py-8 text-center text-slate-400 text-sm">Nessuna singola riga in sospeso.</td></tr>`;
    } else {
      linesData.lines.forEach(line => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-50 transition-colors';
        tr.innerHTML = `
          <td class="py-2.5 px-4 text-center">
            <input type="checkbox" onchange="toggleSelectLine(${line.riga_id}, this.checked)" class="line-checkbox rounded border-slate-300 text-indigo-600 focus:ring-indigo-500">
          </td>
          <td class="py-2.5 px-4">
            <span class="font-bold text-slate-900 block">${line.numero_documento}</span>
            <span class="text-[10px] text-slate-400">${line.data_documento}</span>
          </td>
          <td class="py-2.5 px-4 text-xs font-medium text-slate-700">${line.cedente_denominazione}</td>
          <td class="py-2.5 px-4 font-mono text-xs text-slate-600">${line.riferimento_ddt_numero || '-'}</td>
          <td class="py-2.5 px-4">
            <span class="font-semibold text-slate-800 block text-xs">${line.descrizione}</span>
            <span class="text-[10px] text-slate-400">Riga #${line.numero_linea}</span>
          </td>
          <td class="py-2.5 px-4 text-right font-medium text-xs">${formatQty(line.quantita)} ${line.unita_misura}</td>
          <td class="py-2.5 px-4 text-right font-mono font-bold text-xs text-slate-900">${formatCurrency(line.prezzo_totale_netto)}</td>
          <td class="py-2.5 px-4 text-center">
            ${userHasPermission('fatture.assign') ? `
              <div class="inline-flex space-x-1">
                <button onclick="quickAssignSingleLine(${line.riga_id}, 1)" title="Assegna a Krügel" class="px-2 py-1 text-[11px] font-bold rounded bg-amber-100 text-amber-900 hover:bg-amber-200">
                  🍺 Krügel
                </button>
                <button onclick="quickAssignSingleLine(${line.riga_id}, 2)" title="Assegna a Cafè L’Incontro" class="px-2 py-1 text-[11px] font-bold rounded bg-emerald-100 text-emerald-900 hover:bg-emerald-200">
                  ☕ Incontro
                </button>
              </div>
            ` : '<span class="text-slate-400 text-xs">Sola lettura</span>'}
          </td>
        `;
        tbodyLines.appendChild(tr);
      });
    }

    lucide.createIcons();
  } catch (err) {
    console.error(err);
  }
}

async function quickAssignDoc(docId, sedeId) {
  try {
    const res = await authFetch('/api/unassigned/quick-assign-invoice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ documento_id: docId, sede_id: sedeId })
    });
    const d = await res.json();
    showToast(d.message);
    loadUnassigned();
  } catch (err) {
    console.error(err);
  }
}

async function quickAssignSingleLine(lineId, sedeId) {
  try {
    const res = await authFetch(`/api/lines/${lineId}/assign-venue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sede_id: sedeId })
    });
    const d = await res.json();
    showToast(d.message);
    loadUnassigned();
  } catch (err) {
    console.error(err);
  }
}

function toggleSelectLine(lineId, checked) {
  if (checked) selectedUnassignedLineIds.add(lineId);
  else selectedUnassignedLineIds.delete(lineId);
}

function toggleSelectAllUnassigned(master) {
  const checkboxes = document.querySelectorAll('.line-checkbox');
  checkboxes.forEach(cb => {
    cb.checked = master.checked;
  });
  if (master.checked) {
    authFetch('/api/unassigned/lines').then(r => r.json()).then(d => {
      d.lines.forEach(l => selectedUnassignedLineIds.add(l.riga_id));
    });
  } else {
    selectedUnassignedLineIds.clear();
  }
}

async function batchAssignLines(sedeId) {
  if (!userHasPermission('fatture.assign')) {
    showToast('Non hai il permesso di assegnare le righe.', 'error');
    return;
  }
  if (selectedUnassignedLineIds.size === 0) {
    showToast('Seleziona almeno una riga con la casella di spunta', 'error');
    return;
  }

  try {
    const res = await authFetch('/api/unassigned/quick-assign-lines', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        riga_ids: Array.from(selectedUnassignedLineIds),
        sede_id: sedeId
      })
    });
    const d = await res.json();
    showToast(d.message);
    loadUnassigned();
  } catch (err) {
    console.error(err);
  }
}

async function updateUnassignedBadge() {
  try {
    const res = await authFetch('/api/unassigned/summary');
    const d = await res.json();
    const tot = d.fatture_da_assegnare + d.righe_da_assegnare;
    const badge = document.getElementById('nav-count-unassigned');
    if (badge) {
      if (tot > 0) {
        badge.textContent = tot;
        badge.classList.remove('hidden');
      } else {
        badge.classList.add('hidden');
      }
    }
  } catch (err) {
    // Silenzioso
  }
}

// Configurazione & Sedi
async function loadSettings() {
  await Promise.all([
    loadSediSettings(),
    loadProductsSettings(),
    loadMappingsSettings()
  ]);
}

async function loadSediSettings() {
  const container = document.getElementById('sedi-cards-container');
  container.innerHTML = '';
  try {
    const res = await authFetch('/api/settings/sedi');
    const d = await res.json();

    d.sedi.forEach(s => {
      const card = document.createElement('div');
      const isK = s.nome.includes('Krügel');
      const borderCol = isK ? 'border-amber-300 bg-amber-50/30' : 'border-emerald-300 bg-emerald-50/30';
      const badgeClass = isK ? 'badge-krugel' : 'badge-incontro';

      card.className = `p-5 rounded-xl border ${borderCol} shadow-sm bg-white`;
      card.innerHTML = `
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center space-x-2">
            <span class="text-xl">${isK ? '🍕' : '☕'}</span>
            <h4 class="font-bold text-base text-slate-900">${s.nome}</h4>
          </div>
          <span class="px-2.5 py-0.5 rounded text-xs font-bold ${badgeClass}">Codice: ${s.codice}</span>
        </div>
        <div class="space-y-1 text-xs text-slate-600">
          <p><strong>Indirizzo Consegna:</strong> ${s.indirizzo}, ${s.cap} ${s.comune} (${s.provincia})</p>
          <p><strong>Parole Chiave Riconoscimento:</strong> <span class="font-mono text-slate-500">${s.parole_chiave || 'N.D.'}</span></p>
          <p class="pt-2 text-[11px] text-slate-400">Fatture associate: ${s.tot_fatture_assegnate} • Righe associate: ${s.tot_righe_assegnate}</p>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error(err);
  }
}

async function loadProductsSettings() {
  try {
    const res = await authFetch('/api/settings/products');
    const d = await res.json();
    cachedProducts = d.products || [];

    const sel = document.getElementById('map-select-product');
    sel.innerHTML = '<option value="">-- Crea un nuovo prodotto sotto --</option>';
    cachedProducts.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.nome_canonico} (${p.categoria} - ${p.unita_base})`;
      sel.appendChild(opt);
    });
  } catch (err) {
    console.error(err);
  }
}

async function loadMappingsSettings() {
  const tbody = document.getElementById('mappings-table-body');
  tbody.innerHTML = '';
  try {
    const res = await authFetch('/api/settings/mappings');
    const d = await res.json();
    d.mappings.forEach(m => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-bold text-slate-900">${m.prodotto_nome}</td>
        <td class="py-2.5 px-3 font-bold text-indigo-700">${m.prodotto_um_base}</td>
        <td class="py-2.5 px-3 font-mono font-medium text-slate-700">${m.pattern_testo}</td>
        <td class="py-2.5 px-3 text-slate-600">${m.unita_confezione || '-'}</td>
        <td class="py-2.5 px-3 text-right font-mono font-bold text-indigo-900">${m.fattore_conversione}x</td>
        <td class="py-2.5 px-3 text-slate-500">${m.fornitore_denominazione || 'Tutti i fornitori'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

// Upload XML / ZIP
function openUploadModal() {
  if (!userHasPermission('fatture.import')) {
    showToast('Non hai il permesso di importare fatture.', 'error');
    return;
  }
  filesToUpload = [];
  document.getElementById('upload-file-list').innerHTML = '';
  document.getElementById('btn-submit-upload').disabled = true;
  openModal('modal-upload');

  const dropZone = document.getElementById('drop-zone');
  dropZone.onclick = () => document.getElementById('file-input').click();

  dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('border-indigo-500', 'bg-indigo-50/30'); };
  dropZone.ondragleave = () => { dropZone.classList.remove('border-indigo-500', 'bg-indigo-50/30'); };
  dropZone.ondrop = (e) => {
    e.preventDefault();
    dropZone.classList.remove('border-indigo-500', 'bg-indigo-50/30');
    if (e.dataTransfer.files) handleFiles(e.dataTransfer.files);
  };
}

function handleFileSelect(e) {
  if (e.target.files) handleFiles(e.target.files);
}

function handleFiles(files) {
  filesToUpload = Array.from(files);
  const listEl = document.getElementById('upload-file-list');
  listEl.innerHTML = '';

  filesToUpload.forEach(f => {
    const div = document.createElement('div');
    div.className = 'flex items-center justify-between p-2 rounded bg-slate-100';
    const isZip = f.name.toLowerCase().endsWith('.zip');
    const icon = isZip ? 'archive' : 'file';
    const zipBadge = isZip ? '<span class="ml-2 px-1.5 py-0.2 rounded text-[10px] font-bold bg-indigo-100 text-indigo-700">Archivio ZIP</span>' : '';

    div.innerHTML = `
      <div class="flex items-center space-x-2 truncate">
        <i data-lucide="${icon}" class="w-4 h-4 ${isZip ? 'text-indigo-600' : 'text-slate-500'} flex-shrink-0"></i>
        <span class="truncate font-medium text-slate-700">${f.name}</span>
        ${zipBadge}
      </div>
      <span class="text-[11px] text-slate-400 font-mono">${(f.size / 1024).toFixed(1)} KB</span>
    `;
    listEl.appendChild(div);
  });

  document.getElementById('btn-submit-upload').disabled = filesToUpload.length === 0;
  lucide.createIcons();
}

async function executeUpload() {
  if (filesToUpload.length === 0) return;

  const btn = document.getElementById('btn-submit-upload');
  btn.disabled = true;
  btn.textContent = 'Importazione in corso...';

  const formData = new FormData();
  filesToUpload.forEach(f => formData.append('files', f));

  try {
    const res = await authFetch('/api/invoices/upload', {
      method: 'POST',
      body: formData
    });
    const d = await res.json();

    closeModal('modal-upload');
    showToast(`Importazione completata: ${d.imported} importate, ${d.duplicates} duplicati evitati.`);

    if (currentInvoicesTab === 'invoices') loadInvoices();
    else if (currentInvoicesTab === 'analytics') loadAnalytics();
    else if (currentInvoicesTab === 'unassigned') loadUnassigned();
    updateUnassignedBadge();
  } catch (err) {
    showToast('Errore durante il caricamento dei file XML o ZIP', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Avvia Importazione';
  }
}

// Mappatura Prodotto
function openProductMappingModal(lineData) {
  if (!userHasPermission('fatture.products')) {
    showToast('Non hai il permesso di gestire le associazioni prodotto.', 'error');
    return;
  }
  document.getElementById('map-line-id').value = lineData.id || '';
  document.getElementById('map-original-desc').textContent = lineData.descrizione;
  document.getElementById('map-factor').value = '1.0';
  document.getElementById('map-package-desc').value = '';
  openModal('modal-map-product');
}

async function submitMapProduct(e) {
  e.preventDefault();
  const lineId = document.getElementById('map-line-id').value;
  const pId = document.getElementById('map-select-product').value;
  const factor = parseFloat(document.getElementById('map-factor').value) || 1.0;
  const packDesc = document.getElementById('map-package-desc').value;

  if (!pId) {
    showToast('Seleziona il prodotto canonico a cui associare la descrizione.', 'error');
    return;
  }

  const payload = {
    prodotto_id: parseInt(pId),
    fattore_conversione: factor,
    unita_confezione: packDesc,
    pattern_ricerca: document.getElementById('map-original-desc').textContent
  };

  try {
    let res;
    if (lineId) {
      res = await authFetch(`/api/lines/${lineId}/map-product`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } else {
      res = await authFetch('/api/settings/mappings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prodotto_id: payload.prodotto_id,
          pattern_testo: payload.pattern_ricerca,
          fattore_conversione: factor,
          unita_confezione: packDesc
        })
      });
    }

    const d = await res.json();
    closeModal('modal-map-product');
    showToast(d.message);

    loadProductsSettings();
    if (currentInvoicesTab === 'analytics') loadAnalytics();
    if (currentDetailInvoiceId) openInvoiceDetail(currentDetailInvoiceId);
  } catch (err) {
    console.error(err);
  }
}

function openNewMappingModal() {
  openProductMappingModal({ id: null, descrizione: '' });
}

// Caricamento Dati Demo
async function loadDemoData() {
  if (!currentUser.is_admin) return;
  const btn = document.getElementById('btn-load-demo');
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-amber-500"></i><span>Caricamento...</span>`;
  lucide.createIcons();

  try {
    const res = await authFetch('/api/demo/load', { method: 'POST' });
    const d = await res.json();
    showToast(d.message);
    if (currentInvoicesTab === 'analytics') loadAnalytics();
    else if (currentInvoicesTab === 'invoices') loadInvoices();
    else if (currentInvoicesTab === 'unassigned') loadUnassigned();
  } catch (err) {
    showToast('Errore durante il caricamento dei dati demo', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="sparkles" class="w-4 h-4 text-amber-500"></i><span>Dati Demo</span>`;
    lucide.createIcons();
  }
}

// ==========================================
// 11. INIZIALIZZAZIONE ALL'AVVIO
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
  lucide.createIcons();

  if (authToken) {
    try {
      const res = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        currentUser = data.user;
        navigateToChooseVenue();
        return;
      } else {
        authToken = null;
        localStorage.removeItem('fl_auth_token');
      }
    } catch (e) {
      authToken = null;
      localStorage.removeItem('fl_auth_token');
    }
  }

  showLoginScreen();
});

/* chi-system theme.js — 主題邏輯唯一來源（SPEC.md §6）
 *
 * 用法：在每頁 <head> 以同步方式引入，放在樣式表之前，首次繪製前就會套用主題，
 * 不會閃白或閃黑。不可用 defer 或 async 載入；若該站無法同步引入，改把下方
 * <head> 內嵌片段貼進 <head>（它只做讀取與套用，不綁切換按鈕）。
 *
 *   <script src="https://.../theme.js"></script>（釘版引用，見 SPEC.md §10）
 *   <link rel="stylesheet" href="https://.../tokens.css">
 *
 * <head> 內嵌片段（僅在無法同步引入 theme.js 時使用）：
 *   <script>try{var m=localStorage.getItem('chi-theme-mode');m=(m==='light'||m==='dark')?m:'system';var d=(m==='dark')||(m==='system'&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';document.documentElement.setAttribute('data-chi-theme',d);document.documentElement.setAttribute('data-chi-theme-mode',m);document.documentElement.style.colorScheme=d;}catch(e){}</script>
 *
 * 規則（皆來自 SPEC.md §6）：
 * - 模式固定三態 system／light／dark，預設 system；localStorage key 為 chi-theme-mode，
 *   未設定或值不合法時視為 system；各站不得另寫主題邏輯，框架站只允許一層薄包裝呼叫它。
 * - 實際生效主題寫在 data-chi-theme（light 或 dark），使用者選擇寫在 data-chi-theme-mode。
 * - system 模式跟隨 prefers-color-scheme，系統設定改變時即時跟著變。
 * - localStorage 在每個子域名各自獨立，不承諾跨站同步；舊 key 不搬移，遷移後第一次開啟為 system。
 * - 切換按鈕放在 header（header 版式）或側邊欄底部（側邊欄版式）：<button data-chi-theme-toggle aria-label="...">…</button>，
 *   圖示依目前模式顯示 sun（淺色）／moon（深色）／sun-moon（跟隨系統），點擊依 system→light→dark 循環。
 * - color-scheme 由 tokens.css 依 data-chi-theme 設定（§4）；此檔同時寫入
 *   documentElement.style.colorScheme，只是讓原生控制項在樣式表載入前就跟上，不取代 CSS 的設定。
 * - 對外 API（供框架薄包裝與除錯用）：window.ChiTheme = { getMode, setMode, cycle,
 *   getEffective, setPreviewMode, bindToggles, KEY, MODES }；setPreviewMode 僅供預覽使用、不寫入 localStorage；切換時在 window 派發 chi-theme-change
 *   事件，detail 為 { mode, effective }。
 */
(function () {
  'use strict';

  var KEY = 'chi-theme-mode';
  var MODES = ['system', 'light', 'dark'];
  var ICONS = { system: 'sun-moon', light: 'sun', dark: 'moon' };
  var LABELS = { system: '跟隨系統', light: '淺色', dark: '深色' };
  // 文字圖示使用純文字呈現，避免依賴未隨設計系統提供的外部 SVG sprite。
  var GLYPHS = { system: '◐', light: '☀︎', dark: '☾' };
  var ORDER = ['system', 'light', 'dark'];

  var root = document.documentElement;

  function isMode(value) {
    return value === 'system' || value === 'light' || value === 'dark';
  }

  function readMode() {
    try {
      var value = window.localStorage.getItem(KEY);
      return isMode(value) ? value : 'system';
    } catch (error) {
      return 'system';
    }
  }

  function saveMode(mode) {
    try {
      window.localStorage.setItem(KEY, mode);
    } catch (error) {
      /* 私密瀏覽等無法寫入時，只套用本次開啟的選擇，不報錯 */
    }
  }

  function systemIsDark() {
    try {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    } catch (error) {
      return false;
    }
  }

  function effectiveOf(mode) {
    if (mode === 'dark') return 'dark';
    if (mode === 'light') return 'light';
    return systemIsDark() ? 'dark' : 'light';
  }

  function setIcon(button, mode) {
    var use = button.querySelector('use');
    if (!use) return;
    var href = use.getAttribute('href') || use.getAttribute('xlink:href') || '';
    var base = href.split('#')[0];
    var next = base + '#' + ICONS[mode];
    if (use.hasAttribute('href')) use.setAttribute('href', next);
    if (use.hasAttribute('xlink:href')) use.setAttribute('xlink:href', next);
    if (!use.hasAttribute('href') && !use.hasAttribute('xlink:href')) {
      use.setAttribute('href', next);
    }
  }

  function updateButtons(mode) {
    var buttons = document.querySelectorAll('[data-chi-theme-toggle]');
    for (var i = 0; i < buttons.length; i++) {
      var button = buttons[i];
      setIcon(button, mode);
      var icon = button.querySelector('[data-chi-theme-icon]');
      if (icon) icon.textContent = GLYPHS[mode];
      var label = '目前色彩模式：' + LABELS[mode] + '，點擊切換';
      button.setAttribute('aria-label', label);
      // 原生 title 也同步，避免滑鼠提示仍停留在初始的泛用文案。
      button.setAttribute('title', label);
    }
  }

  function dispatchChange(mode, effective) {
    try {
      var event = new window.CustomEvent('chi-theme-change', {
        detail: { mode: mode, effective: effective },
      });
      window.dispatchEvent(event);
    } catch (error) {
      /* 舊環境無 CustomEvent 時略過，不影響主題套用 */
    }
  }

  var currentMode = readMode();

  function apply(mode) {
    currentMode = mode;
    var effective = effectiveOf(mode);
    root.setAttribute('data-chi-theme', effective);
    root.setAttribute('data-chi-theme-mode', mode);
    root.style.colorScheme = effective;
    updateButtons(mode);
    dispatchChange(mode, effective);
  }

  function setMode(mode) {
    if (!isMode(mode)) return;
    saveMode(mode);
    apply(mode);
  }

  // 預覽頁設定主題時只改當前頁面，不污染正式網站的使用者偏好。
  function setPreviewMode(mode) {
    if (!isMode(mode)) return;
    apply(mode);
  }

  function cycle() {
    var next = ORDER[(ORDER.indexOf(currentMode) + 1) % ORDER.length];
    setMode(next);
    return next;
  }

  function bindToggles() {
    var buttons = document.querySelectorAll('[data-chi-theme-toggle]');
    for (var i = 0; i < buttons.length; i++) {
      var button = buttons[i];
      if (button.__chiThemeBound) continue;
      button.__chiThemeBound = true;
      button.addEventListener('click', cycle);
    }
    updateButtons(currentMode);
  }

  /* 系統設定改變時，若目前為 system 模式即時跟著變；固定模式不受影響 */
  try {
    var media = window.matchMedia('(prefers-color-scheme: dark)');
    var onSystemChange = function () {
      if (currentMode === 'system') apply('system');
    };
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', onSystemChange);
    } else if (typeof media.addListener === 'function') {
      media.addListener(onSystemChange);
    }
  } catch (error) {
    /* 無 matchMedia 時略過，預設以淺色呈現 */
  }

  /* 立即套用（本檔在 <head> 同步執行時，發生在首次繪製之前）；切換按鈕等 DOM 備妥後再綁定 */
  apply(currentMode);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindToggles);
  } else {
    bindToggles();
  }

  window.ChiTheme = {
    KEY: KEY,
    MODES: MODES.slice(),
    getMode: function () {
      return currentMode;
    },
    getEffective: function () {
      return effectiveOf(currentMode);
    },
    setMode: setMode,
    setPreviewMode: setPreviewMode,
    cycle: cycle,
    bindToggles: bindToggles,
  };
})();
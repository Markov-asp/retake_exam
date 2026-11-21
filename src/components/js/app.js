(function () {
  'use strict';

  const state = {
    catalog: null,
    reports: [],
    view: 'dashboard',
    sheet: 'details',
    granularity: 'day',
    aggregation: 'avg',
    dateFrom: '',
    dateTo: '',
    reportId: '',
    search: '',
    page: 0,
    pageSize: 25,
    sort: 'date',
    order: 'desc',
    theme: localStorage.getItem('ds-theme') === 'dark' ? 'dark' : 'light',
    dashboard: null,
    table: null,
    pendingFile: null,
    uploading: false,
  };

  const dom = {};
  let dashboardToken = 0;
  let tableToken = 0;

  const numberFormatters = new Map();

  function numberFormat(decimals) {
    const key = String(decimals);
    if (!numberFormatters.has(key)) {
      numberFormatters.set(key, new Intl.NumberFormat('ru-RU', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }));
    }
    return numberFormatters.get(key);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function debounce(fn, wait) {
    let timer = null;
    return function () {
      const args = arguments;
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(null, args), wait);
    };
  }

  function plural(count, one, few, many) {
    const value = Math.abs(Number(count)) % 100;
    const tail = value % 10;
    if (value > 10 && value < 20) return many;
    if (tail === 1) return one;
    if (tail >= 2 && tail <= 4) return few;
    return many;
  }

  function formatDate(value) {
    if (!value) return '—';
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return String(value);
    return match[3] + '.' + match[2] + '.' + match[1];
  }

  function humanDuration(seconds) {
    const total = Math.round(Number(seconds));
    if (!isFinite(total) || total < 0) return '—';
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hours) return hours + 'ч ' + String(minutes).padStart(2, '0') + 'м ' + String(secs).padStart(2, '0') + 'с';
    return minutes + 'м ' + String(secs).padStart(2, '0') + 'с';
  }

  function formatCell(value, column) {
    if (value === null || value === undefined || value === '') return '—';
    if (column.format === 'date') return formatDate(value);
    if (column.format === 'duration') return humanDuration(value);
    if (column.kind === 'integer') return numberFormat(0).format(Number(value));
    if (column.kind === 'number') {
      const decimals = column.decimals === undefined ? 2 : column.decimals;
      const number = Number(value);
      return isFinite(number) ? numberFormat(decimals).format(number) : String(value);
    }
    return String(value);
  }

  function totalRows() {
    return state.reports.reduce((sum, report) => sum + (report.details_rows || 0) + (report.trackers_rows || 0), 0);
  }

  function toast(message, type) {
    const node = el('div', 'toast toast--' + (type || 'info'), message);
    dom.toast.appendChild(node);
    setTimeout(() => {
      node.style.opacity = '0';
      node.style.transform = 'translateY(6px)';
      setTimeout(() => node.remove(), 220);
    }, 4200);
  }

  function applyTheme() {
    document.documentElement.dataset.theme = state.theme;
    dom.themeToggle.title = state.theme === 'dark' ? 'Светлая тема' : 'Тёмная тема';
  }

  function showView(view) {
    state.view = view;
    const isDashboard = view === 'dashboard';
    dom.viewDashboard.classList.toggle('is-hidden', !isDashboard);
    dom.viewReports.classList.toggle('is-hidden', isDashboard);
    dom.navButtons.forEach((button) => {
      button.classList.toggle('is-active', button.dataset.view === view);
    });
    dom.pageTitle.textContent = isDashboard ? 'Дашборд' : 'Отчёты';
    dom.pageSubtitle.textContent = isDashboard
      ? 'Технические характеристики видео и телеметрия трекинга'
      : 'Управление загруженными файлами и результатами обработки';
    if (!isDashboard) renderReports();
  }

  function showEmpty(show) {
    dom.emptyState.classList.toggle('is-hidden', !show);
    dom.viewDashboard.classList.toggle('is-hidden', show || state.view !== 'dashboard');
    dom.viewReports.classList.toggle('is-hidden', show || state.view !== 'reports');
  }

  /* --------------------------------------------------------------- catalog */
  async function loadCatalog() {
    state.catalog = await window.API.catalog();
    const sheet = state.sheet;
    dom.sheetTabs.innerHTML = '';
    state.catalog.sheets.forEach((sheetInfo) => {
      const button = el('button', 'sheet-tab' + (sheetInfo.key === sheet ? ' is-active' : ''));
      button.type = 'button';
      button.dataset.sheet = sheetInfo.key;
      button.setAttribute('role', 'tab');
      button.append(el('span', null, sheetInfo.title));
      const count = el('span', 'tab-count', '0');
      count.dataset.sheetCount = sheetInfo.key;
      button.append(count);
      button.addEventListener('click', () => {
        if (state.sheet === sheetInfo.key) return;
        state.sheet = sheetInfo.key;
        state.page = 0;
        state.sort = 'date';
        state.order = 'desc';
        dom.sheetTabs.querySelectorAll('.sheet-tab').forEach((tab) => {
          tab.classList.toggle('is-active', tab.dataset.sheet === state.sheet);
          tab.setAttribute('aria-selected', tab.dataset.sheet === state.sheet ? 'true' : 'false');
        });
        loadDashboard();
        loadTable();
      });
      dom.sheetTabs.append(button);
    });

    dom.granularity.innerHTML = '';
    state.catalog.granularities.forEach((item) => {
      const button = el('button', item.key === state.granularity ? 'is-active' : '', item.title);
      button.type = 'button';
      button.dataset.granularity = item.key;
      button.setAttribute('aria-pressed', item.key === state.granularity ? 'true' : 'false');
      button.addEventListener('click', () => {
        if (state.granularity === item.key) return;
        state.granularity = item.key;
        dom.granularity.querySelectorAll('button').forEach((btn) => {
          btn.classList.toggle('is-active', btn.dataset.granularity === state.granularity);
          btn.setAttribute('aria-pressed', btn.dataset.granularity === state.granularity ? 'true' : 'false');
        });
        loadDashboard();
      });
      dom.granularity.append(button);
    });

    dom.aggregation.innerHTML = '';
    state.catalog.aggregations.forEach((item) => {
      const option = el('option', null, item.title);
      option.value = item.key;
      if (item.key === state.aggregation) option.selected = true;
      dom.aggregation.append(option);
    });
  }

  function sheetCounts() {
    const counts = { details: 0, trackers: 0 };
    state.reports.forEach((report) => {
      counts.details += report.details_rows || 0;
      counts.trackers += report.trackers_rows || 0;
    });
    return counts;
  }

  function updateSheetCounts() {
    const counts = sheetCounts();
    dom.sheetTabs.querySelectorAll('[data-sheet-count]').forEach((node) => {
      node.textContent = String(counts[node.dataset.sheetCount] || 0);
    });
  }

  /* --------------------------------------------------------------- reports */
  async function refreshReports() {
    const data = await window.API.reports();
    state.reports = data.items || [];

    if (state.reportId && !state.reports.some((report) => report.id === state.reportId)) {
      state.reportId = '';
    }

    dom.reportsCount.textContent = String(state.reports.length);
    renderReportSelect();
    renderReports();
    updateSheetCounts();

    const empty = state.reports.length === 0;
    showEmpty(empty);
    if (!empty) {
      dom.viewDashboard.classList.toggle('is-hidden', state.view !== 'dashboard');
      dom.viewReports.classList.toggle('is-hidden', state.view !== 'reports');
    }
    return data;
  }

  function renderReportSelect() {
    dom.reportSelect.innerHTML = '';
    const all = el('option', null, 'Все отчёты (' + state.reports.length + ')');
    all.value = '';
    dom.reportSelect.append(all);
    state.reports.forEach((report) => {
      const option = el('option', null, report.title + ' · ' + (report.details_rows + report.trackers_rows) + ' стр.');
      option.value = report.id;
      if (report.id === state.reportId) option.selected = true;
      dom.reportSelect.append(option);
    });
    dom.reportSelect.disabled = state.reports.length === 0;
  }

  function statusLabel(status) {
    if (status === 'failed') return 'Ошибка';
    if (status === 'processing') return 'Обработка';
    return 'Готов';
  }

  function renderReports() {
    dom.reportList.innerHTML = '';
    if (!state.reports.length) {
      const card = el('div', 'empty-card');
      card.append(el('h2', null, 'Отчётов пока нет'));
      card.append(el('p', null, 'Загрузите Excel-файл с листами «Детали» и «Трекеры».'));
      dom.reportList.append(card);
      return;
    }

    state.reports.forEach((report) => {
      const card = el('article', 'report-card');
      const head = el('div', 'report-card-head');
      const info = el('div');
      info.append(el('h3', null, report.title));
      info.append(el('p', 'report-file', report.filename));
      const pill = el('span', 'status-pill ' + (report.status === 'failed' ? 'status-failed' : 'status-ready'), statusLabel(report.status));
      head.append(info, pill);

      const stats = el('div', 'report-stats');
      [['Эпизодов', report.details_rows], ['Трекинга', report.trackers_rows], ['Пропущено', report.skipped_rows]].forEach((pair) => {
        const block = el('div', 'report-stat');
        block.append(el('span', null, pair[0]));
        block.append(el('b', null, String(pair[1])));
        stats.append(block);
      });

      const meta = el('p', 'muted small', 'Загружен ' + formatDateTime(report.uploaded_at) + (report.message ? ' · ' + report.message : ''));

      const actions = el('div', 'report-actions');
      const open = el('button', 'btn btn-primary btn-sm', 'Показать');
      open.type = 'button';
      open.addEventListener('click', () => {
        state.reportId = report.id;
        dom.reportSelect.value = report.id;
        state.page = 0;
        showView('dashboard');
        loadDashboard();
        loadTable();
      });

      const download = el('a', 'btn btn-ghost btn-sm', 'Скачать');
      download.href = window.API.downloadUrl(report.id);
      download.setAttribute('download', '');

      const remove = el('button', 'btn btn-ghost btn-sm', 'Удалить');
      remove.type = 'button';
      remove.addEventListener('click', () => removeReport(report));

      actions.append(open, download, remove);
      card.append(head, stats, meta, actions);
      dom.reportList.append(card);
    });
  }

  function formatDateTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    return date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  async function removeReport(report) {
    if (!window.confirm('Удалить отчёт «' + report.title + '»? Данные будут удалены безвозвратно.')) return;
    try {
      await window.API.deleteReport(report.id);
      toast('Отчёт удалён', 'success');
      if (state.reportId === report.id) state.reportId = '';
      await refreshReports();
      if (state.reports.length) {
        await Promise.all([loadDashboard(), loadTable()]);
      }
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  /* -------------------------------------------------------------- dashboard */
  function dashboardParams() {
    return {
      sheet: state.sheet,
      granularity: state.granularity,
      aggregation: state.aggregation,
      date_from: state.dateFrom,
      date_to: state.dateTo,
      report_id: state.reportId,
      theme: state.theme,
    };
  }

  function renderKpis(kpis) {
    dom.kpiGrid.innerHTML = '';
    (kpis || []).forEach((kpi) => {
      const card = el('article', 'kpi-card');
      card.dataset.tone = kpi.tone || 'neutral';
      card.append(el('div', 'kpi-label', kpi.label));
      const value = el('div', 'kpi-value');
      value.append(el('span', null, kpi.display));
      if (kpi.unit) value.append(el('span', 'kpi-unit', kpi.unit));
      card.append(value);
      if (kpi.hint) card.append(el('div', 'kpi-hint', kpi.hint));
      dom.kpiGrid.append(card);
    });
  }

  function renderDashboardSkeleton() {
    dom.charts.innerHTML = '';
    const grid = el('div', 'chart-grid');
    for (let index = 0; index < 4; index += 1) {
      const card = el('article', 'chart-card');
      const head = el('div', 'chart-card-head');
      head.append(el('div', 'chart-skeleton'));
      card.append(head);
      grid.append(card);
    }
    dom.charts.append(grid);
    dom.kpiGrid.innerHTML = '';
  }

  function buildChartCard(chart) {
    const card = el('article', 'chart-card');
    const head = el('div', 'chart-card-head');
    const info = el('div');
    info.style.minWidth = '0';
    info.append(el('h3', null, chart.title));
    info.append(el('p', 'chart-card-sub', chart.meta.summary || ''));
    head.append(info);
    if (chart.unit) head.append(el('span', 'badge', chart.unit));
    const body = el('div', 'chart-body');
    card.append(head, body);
    card._chartBody = body;
    card._figure = chart.figure;
    return card;
  }

  function renderCharts(data) {
    window.Charts.purgeAll();
    dom.charts.innerHTML = '';

    if (!data.charts || !data.charts.length) {
      dom.charts.append(el('p', 'muted', 'Нет метрик для отображения'));
      return;
    }

    const groups = new Map();
    data.charts.forEach((chart) => {
      const key = chart.group || 'Метрики';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(chart);
    });

    const cards = [];
    groups.forEach((charts, group) => {
      const section = el('section', 'chart-section');
      section.append(el('h2', 'chart-section-title', group));
      const grid = el('div', 'chart-grid');
      charts.forEach((chart) => {
        const card = buildChartCard(chart);
        cards.push(card);
        grid.append(card);
      });
      section.append(grid);
      dom.charts.append(section);
    });

    cards.forEach((card) => window.Charts.render(card._chartBody, card._figure));
  }

  async function loadDashboard() {
    const token = ++dashboardToken;
    renderDashboardSkeleton();

    try {
      const data = await window.API.dashboard(dashboardParams());
      if (token !== dashboardToken) return;
      state.dashboard = data;
      renderKpis(data.kpis);
      if (data.total_rows === 0) {
        dom.charts.innerHTML = '';
        const notice = el('div', 'panel');
        notice.style.padding = '32px';
        notice.style.textAlign = 'center';
        notice.append(el('h3', null, 'Нет данных по выбранным фильтрам'));
        notice.append(el('p', 'muted', 'Измените период или выберите другой отчёт.'));
        dom.charts.append(notice);
        return;
      }
      renderCharts(data);
      dom.sheetTabs.querySelectorAll('[data-sheet-count]').forEach((node) => {
        if (node.dataset.sheetCount === data.sheet) node.textContent = String(data.total_rows);
      });
    } catch (error) {
      if (token !== dashboardToken) return;
      dom.charts.innerHTML = '';
      const notice = el('div', 'panel');
      notice.style.padding = '28px';
      notice.append(el('h3', null, 'Не удалось построить дашборд'));
      notice.append(el('p', 'muted', error.message));
      dom.charts.append(notice);
      toast(error.message, 'error');
    }
  }

  /* ------------------------------------------------------------------ table */
  function tableParams() {
    return {
      limit: state.pageSize,
      offset: state.page * state.pageSize,
      sort: state.sort,
      order: state.order,
      search: state.search,
      date_from: state.dateFrom,
      date_to: state.dateTo,
      report_id: state.reportId,
    };
  }

  function renderTableHead(columns) {
    dom.tableHead.innerHTML = '';
    const row = el('tr');
    columns.forEach((column) => {
      const th = el('th', column.kind === 'number' || column.kind === 'integer' ? 'numeric' : '');
      th.textContent = column.title;
      th.title = column.description || column.title;
      th.dataset.key = column.key;
      if (state.sort === column.key) {
        th.classList.add('is-sorted');
        if (state.order === 'asc') th.classList.add('is-asc');
      }
      th.addEventListener('click', () => {
        if (state.sort === column.key) {
          state.order = state.order === 'asc' ? 'desc' : 'asc';
        } else {
          state.sort = column.key;
          state.order = 'asc';
        }
        state.page = 0;
        loadTable();
      });
      row.append(th);
    });
    dom.tableHead.append(row);
  }

  function renderTable(data) {
    renderTableHead(data.columns);
    dom.tableBody.innerHTML = '';

    data.rows.forEach((record) => {
      const row = el('tr');
      data.columns.forEach((column) => {
        const value = record[column.key];
        const cell = el('td', column.kind === 'number' || column.kind === 'integer' ? 'numeric' : '');
        if (value === null || value === undefined || value === '') {
          cell.textContent = '—';
          cell.classList.add('cell-muted');
        } else if (column.key === 'category') {
          const chip = el('span', 'cell-chip', String(value));
          cell.append(chip);
        } else {
          cell.textContent = formatCell(value, column);
        }
        row.append(cell);
      });
      dom.tableBody.append(row);
    });

    const hasRows = data.rows.length > 0;
    dom.tableEmpty.classList.toggle('is-hidden', hasRows);

    const pages = Math.max(1, Math.ceil(data.total / state.pageSize));
    if (state.page >= pages) state.page = pages - 1;
    dom.pageLabel.textContent = (state.page + 1) + ' / ' + pages;
    dom.pagePrev.disabled = state.page <= 0;
    dom.pageNext.disabled = state.page >= pages - 1;
    dom.tableRange.textContent = hasRows
      ? (data.offset + 1) + '–' + (data.offset + data.rows.length) + ' из ' + data.total
      : '0 из ' + data.total;
    dom.tableSubtitle.textContent = data.total
      ? data.total + ' ' + plural(data.total, 'запись', 'записи', 'записей') + ' · ' + (state.sheet === 'details' ? 'детали видео' : 'телеметрия трекинга')
      : 'Нет записей по выбранным фильтрам';
  }

  async function loadTable() {
    const token = ++tableToken;
    dom.tableBody.innerHTML = '';
    dom.tableRange.textContent = 'Загрузка…';
    try {
      const data = await window.API.table(state.sheet, tableParams());
      if (token !== tableToken) return;
      state.table = data;
      renderTable(data);
    } catch (error) {
      if (token !== tableToken) return;
      dom.tableEmpty.classList.remove('is-hidden');
      dom.tableEmpty.textContent = 'Ошибка загрузки таблицы: ' + error.message;
    }
  }

  /* --------------------------------------------------------------- handlers */
  function refreshAll() {
    return Promise.all([loadDashboard(), loadTable()]);
  }

  function bindEvents() {
    dom.navButtons.forEach((button) => {
      button.addEventListener('click', () => showView(button.dataset.view));
    });

    dom.reportSelect.addEventListener('change', () => {
      state.reportId = dom.reportSelect.value;
      state.page = 0;
      refreshAll();
    });

    dom.dateFrom.addEventListener('change', () => {
      state.dateFrom = dom.dateFrom.value;
      state.page = 0;
      refreshAll();
    });
    dom.dateTo.addEventListener('change', () => {
      state.dateTo = dom.dateTo.value;
      state.page = 0;
      refreshAll();
    });

    dom.aggregation.addEventListener('change', () => {
      state.aggregation = dom.aggregation.value;
      loadDashboard();
    });

    dom.resetFilters.addEventListener('click', () => {
      state.dateFrom = '';
      state.dateTo = '';
      state.reportId = '';
      state.search = '';
      state.page = 0;
      state.granularity = 'day';
      state.aggregation = 'avg';
      dom.dateFrom.value = '';
      dom.dateTo.value = '';
      dom.reportSelect.value = '';
      dom.tableSearch.value = '';
      dom.aggregation.value = 'avg';
      dom.granularity.querySelectorAll('button').forEach((button) => {
        button.classList.toggle('is-active', button.dataset.granularity === 'day');
      });
      refreshAll();
    });

    dom.tableSearch.addEventListener('input', debounce(() => {
      state.search = dom.tableSearch.value.trim();
      state.page = 0;
      loadTable();
    }, 320));

    dom.pagePrev.addEventListener('click', () => {
      if (state.page > 0) {
        state.page -= 1;
        loadTable();
      }
    });
    dom.pageNext.addEventListener('click', () => {
      const pages = state.table ? Math.max(1, Math.ceil(state.table.total / state.pageSize)) : 1;
      if (state.page < pages - 1) {
        state.page += 1;
        loadTable();
      }
    });

    document.querySelectorAll('[data-export]').forEach((button) => {
      button.addEventListener('click', () => {
        const format = button.dataset.export;
        const params = {
          search: state.search,
          date_from: state.dateFrom,
          date_to: state.dateTo,
          report_id: state.reportId,
        };
        window.location.href = window.API.exportUrl(state.sheet, format, params);
      });
    });

    dom.themeToggle.addEventListener('click', () => {
      state.theme = state.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('ds-theme', state.theme);
      applyTheme();
      if (state.dashboard) loadDashboard();
    });

    dom.uploadOpen.addEventListener('click', openModal);
    if (dom.uploadOpen2) dom.uploadOpen2.addEventListener('click', openModal);
    dom.emptyUpload.addEventListener('click', openModal);
    document.querySelectorAll('[data-close-modal]').forEach((node) => {
      node.addEventListener('click', closeModal);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !dom.modal.hidden) closeModal();
    });

    dom.dropzone.addEventListener('click', () => dom.fileInput.click());
    dom.dropzone.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        dom.fileInput.click();
      }
    });
    dom.fileInput.addEventListener('change', () => {
      if (dom.fileInput.files.length) setPendingFile(dom.fileInput.files[0]);
    });
    ['dragenter', 'dragover'].forEach((name) => {
      dom.dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dom.dropzone.classList.add('is-drag');
      });
    });
    ['dragleave', 'drop'].forEach((name) => {
      dom.dropzone.addEventListener(name, (event) => {
        event.preventDefault();
        dom.dropzone.classList.remove('is-drag');
      });
    });
    dom.dropzone.addEventListener('drop', (event) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) {
        try { dom.fileInput.files = files; } catch (error) { /* браузер может запретить подмену */ }
        setPendingFile(files[0]);
      }
    });

    dom.fileClear.addEventListener('click', () => setPendingFile(null));
    dom.uploadSubmit.addEventListener('click', submitUpload);
  }

  /* ---------------------------------------------------------------- upload */
  function openModal() {
    dom.modal.hidden = false;
    document.body.style.overflow = 'hidden';
    dom.dropzone.style.pointerEvents = '';
    dom.progress.classList.add('is-hidden');
    dom.progressBar.style.width = '0%';
    setTimeout(() => dom.dropzone.focus(), 50);
  }

  function closeModal() {
    if (state.uploading) return;
    dom.modal.hidden = true;
    document.body.style.overflow = '';
    setPendingFile(null);
    dom.reportTitle.value = '';
  }

  function setPendingFile(file) {
    state.pendingFile = file || null;
    if (!file) {
      dom.fileChip.classList.add('is-hidden');
      dom.uploadSubmit.disabled = true;
      dom.fileInput.value = '';
      return;
    }
    const name = file.name || '';
    const allowed = /\.(xlsx|xlsm)$/i.test(name);
    if (!allowed) {
      toast('Нужен файл .xlsx или .xlsm', 'error');
      state.pendingFile = null;
      dom.uploadSubmit.disabled = true;
      return;
    }
    dom.fileName.textContent = name;
    dom.fileSize.textContent = formatBytes(file.size);
    dom.fileChip.classList.remove('is-hidden');
    dom.uploadSubmit.disabled = false;
  }

  function formatBytes(bytes) {
    if (!bytes) return '0 Б';
    const units = ['Б', 'КБ', 'МБ', 'ГБ'];
    const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    return (bytes / Math.pow(1024, index)).toFixed(index ? 1 : 0) + ' ' + units[index];
  }

  function setUploading(active, progress) {
    state.uploading = active;
    dom.uploadSubmit.disabled = active || !state.pendingFile;
    dom.uploadSubmit.textContent = active ? 'Обработка…' : 'Загрузить и обработать';
    dom.dropzone.style.pointerEvents = active ? 'none' : '';
    dom.progress.classList.toggle('is-hidden', !active && !progress);
    dom.progressBar.style.width = Math.round((progress || 0) * 100) + '%';
  }

  async function submitUpload() {
    if (!state.pendingFile || state.uploading) return;
    setUploading(true, 0);
    try {
      const result = await window.API.upload(state.pendingFile, dom.reportTitle.value, (progress) => {
        setUploading(true, progress);
      });
      toast(result.message, 'success');
      state.uploading = false;
      dom.modal.hidden = true;
      document.body.style.overflow = '';
      setPendingFile(null);
      dom.reportTitle.value = '';
      dom.progress.classList.add('is-hidden');
      dom.progressBar.style.width = '0%';
      state.page = 0;
      state.reportId = result.report.id;
      await refreshReports();
      await refreshAll();
      showView('dashboard');
    } catch (error) {
      toast(error.message, 'error');
      setUploading(false, 0);
    }
  }

  /* ------------------------------------------------------------------ init */
  async function checkHealth() {
    try {
      const health = await window.API.health();
      dom.healthText.textContent = 'работает · ' + health.reports + ' ' + plural(health.reports, 'отчёт', 'отчёта', 'отчётов');
      dom.healthDot.parentElement.classList.add('is-ok');
      dom.healthDot.parentElement.classList.remove('is-error');
    } catch (error) {
      dom.healthText.textContent = 'нет связи';
      dom.healthDot.parentElement.classList.add('is-error');
      dom.healthDot.parentElement.classList.remove('is-ok');
    }
  }

  function applyUrlState() {
    const params = new URLSearchParams(window.location.search);
    const sheet = params.get('sheet');
    if (sheet === 'details' || sheet === 'trackers') state.sheet = sheet;
    const granularity = params.get('granularity');
    if (['day', 'month', 'all'].indexOf(granularity) !== -1) state.granularity = granularity;
    const aggregation = params.get('aggregation');
    if (['avg', 'sum', 'min', 'max'].indexOf(aggregation) !== -1) state.aggregation = aggregation;
    const theme = params.get('theme');
    if (theme === 'dark' || theme === 'light') {
      state.theme = theme;
      localStorage.setItem('ds-theme', theme);
    }
    const view = params.get('view');
    if (view === 'reports' || view === 'dashboard') state.view = view;
    const report = params.get('report');
    if (report) state.reportId = report;
  }

  async function init() {
    dom.viewDashboard = document.getElementById('view-dashboard');
    dom.viewReports = document.getElementById('view-reports');
    dom.emptyState = document.getElementById('empty-state');
    dom.navButtons = Array.from(document.querySelectorAll('.nav-item'));
    dom.pageTitle = document.getElementById('page-title');
    dom.pageSubtitle = document.getElementById('page-subtitle');
    dom.sheetTabs = document.getElementById('sheet-tabs');
    dom.granularity = document.getElementById('granularity');
    dom.aggregation = document.getElementById('aggregation');
    dom.dateFrom = document.getElementById('date-from');
    dom.dateTo = document.getElementById('date-to');
    dom.resetFilters = document.getElementById('reset-filters');
    dom.reportSelect = document.getElementById('report-select');
    dom.reportsCount = document.getElementById('reports-count');
    dom.kpiGrid = document.getElementById('kpi-grid');
    dom.charts = document.getElementById('charts');
    dom.tableHead = document.getElementById('table-head');
    dom.tableBody = document.getElementById('table-body');
    dom.tableEmpty = document.getElementById('table-empty');
    dom.tableSubtitle = document.getElementById('table-subtitle');
    dom.tableSearch = document.getElementById('table-search');
    dom.tableRange = document.getElementById('table-range');
    dom.pageLabel = document.getElementById('page-label');
    dom.pagePrev = document.getElementById('page-prev');
    dom.pageNext = document.getElementById('page-next');
    dom.reportList = document.getElementById('report-list');
    dom.themeToggle = document.getElementById('theme-toggle');
    dom.uploadOpen = document.getElementById('upload-open');
    dom.uploadOpen2 = document.getElementById('upload-open-2');
    dom.emptyUpload = document.getElementById('empty-upload');
    dom.modal = document.getElementById('upload-modal');
    dom.dropzone = document.getElementById('dropzone');
    dom.fileInput = document.getElementById('file-input');
    dom.fileChip = document.getElementById('file-chip');
    dom.fileName = document.getElementById('file-name');
    dom.fileSize = document.getElementById('file-size');
    dom.fileClear = document.getElementById('file-clear');
    dom.reportTitle = document.getElementById('report-title');
    dom.uploadSubmit = document.getElementById('upload-submit');
    dom.progress = document.getElementById('upload-progress');
    dom.progressBar = document.getElementById('progress-bar');
    dom.toast = document.getElementById('toast');
    dom.healthDot = document.getElementById('health-dot');
    dom.healthText = document.getElementById('health-text');

    applyUrlState();
    applyTheme();
    bindEvents();

    try {
      await loadCatalog();
      await refreshReports();
      if (state.reports.length) {
        showEmpty(false);
        showView(state.view);
        await refreshAll();
      } else {
        showEmpty(true);
      }
      checkHealth();
      setInterval(checkHealth, 60000);
    } catch (error) {
      toast('Не удалось запустить интерфейс: ' + error.message, 'error');
      showEmpty(true);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

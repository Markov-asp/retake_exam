(function (global) {
  'use strict';

  function errorMessage(payload, fallback) {
    if (payload && typeof payload === 'object') {
      if (payload.error && payload.error.message) return payload.error.message;
      if (payload.detail) {
        if (typeof payload.detail === 'string') return payload.detail;
        if (Array.isArray(payload.detail) && payload.detail.length) {
          return payload.detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
        }
      }
    }
    if (typeof payload === 'string' && payload.trim() && payload.length < 300) return payload;
    return fallback;
  }

  async function request(path, options) {
    const response = await fetch(path, Object.assign({
      headers: { Accept: 'application/json' },
    }, options || {}));

    const type = response.headers.get('content-type') || '';
    const payload = type.indexOf('application/json') !== -1
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      throw new Error(errorMessage(payload, 'Не удалось выполнить запрос (' + response.status + ')'));
    }
    return payload;
  }

  function query(params) {
    const search = new URLSearchParams();
    Object.keys(params || {}).forEach((key) => {
      const value = params[key];
      if (value === undefined || value === null || value === '') return;
      search.append(key, value);
    });
    const text = search.toString();
    return text ? '?' + text : '';
  }

  function upload(file, title, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/reports');
      xhr.responseType = 'json';

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && typeof onProgress === 'function') {
          onProgress(event.loaded / event.total);
        }
      };

      xhr.onload = () => {
        const payload = xhr.response;
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload);
        } else {
          reject(new Error(errorMessage(payload, 'Ошибка загрузки (' + xhr.status + ')')));
        }
      };
      xhr.onerror = () => reject(new Error('Сеть недоступна — не удалось загрузить файл'));

      const body = new FormData();
      body.append('file', file);
      if (title && title.trim()) body.append('title', title.trim());
      xhr.send(body);
    });
  }

  global.API = {
    query: query,
    catalog: () => request('/api/catalog'),
    health: () => request('/api/health'),
    reports: () => request('/api/reports'),
    upload: upload,
    deleteReport: (id) => request('/api/reports/' + encodeURIComponent(id), { method: 'DELETE' }),
    dashboard: (params) => request('/api/dashboard' + query(params)),
    table: (sheet, params) => request('/api/table/' + encodeURIComponent(sheet) + query(params)),
    chart: (sheet, metric, params) => request(
      '/api/charts/' + encodeURIComponent(sheet) + '/' + encodeURIComponent(metric) + query(params)
    ),
    exportUrl: (sheet, format, params) => '/api/export/' + encodeURIComponent(sheet) + '.' + format + query(params),
    downloadUrl: (id) => '/api/reports/' + encodeURIComponent(id) + '/download',
  };
})(window);

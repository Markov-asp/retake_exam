(function (global) {
  'use strict';

  const plots = new Set();

  const config = {
    responsive: true,
    displaylogo: false,
    displayModeBar: 'hover',
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines', 'hoverCompareCartesian'],
    toImageButtonOptions: { format: 'png', filename: 'datascope-chart', scale: 2 },
  };

  function render(container, figure) {
    if (!global.Plotly) {
      container.textContent = 'Не удалось загрузить библиотеку графиков';
      return;
    }
    if (!figure || !figure.data) {
      container.textContent = 'Нет данных для графика';
      return;
    }
    global.Plotly.react(container, figure.data, figure.layout || {}, config);
    plots.add(container);
  }

  function purgeAll() {
    plots.forEach((node) => {
      try {
        global.Plotly.purge(node);
      } catch (error) {
        /* узел мог быть удалён из DOM */
      }
    });
    plots.clear();
  }

  function resizeAll() {
    plots.forEach((node) => {
      if (!node.isConnected) return;
      try {
        global.Plotly.Plots.resize(node);
      } catch (error) {
        /* игнорируем переходные состояния */
      }
    });
  }

  let resizeTimer = null;
  global.addEventListener('resize', () => {
    global.clearTimeout(resizeTimer);
    resizeTimer = global.setTimeout(resizeAll, 150);
  });

  global.Charts = { render: render, purgeAll: purgeAll, resizeAll: resizeAll };
})(window);

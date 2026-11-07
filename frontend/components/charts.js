// ============================================================
// CHART COMPONENTS — Chart.js wrappers
// ============================================================

import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

// Global Chart.js defaults for brutalist light theme
Chart.defaults.color = '#000000';
Chart.defaults.borderColor = '#E0DCD5';
Chart.defaults.font.family = "'Helvetica Neue', Arial, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#FFFFFF';
Chart.defaults.plugins.tooltip.titleColor = '#000000';
Chart.defaults.plugins.tooltip.bodyColor = '#000000';
Chart.defaults.plugins.tooltip.borderColor = '#000000';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 0;
Chart.defaults.plugins.tooltip.titleFont = { family: "'Helvetica Neue', sans-serif", size: 12, weight: '700' };
Chart.defaults.plugins.tooltip.bodyFont = { family: "'Helvetica Neue', sans-serif", size: 11 };

// Store chart instances for cleanup
const chartInstances = {};

function destroyChart(id) {
  if (chartInstances[id]) {
    chartInstances[id].destroy();
    delete chartInstances[id];
  }
}

/**
 * Create a line/area chart
 */
export function createLineChart(canvasId, labels, datasets, options = {}) {
  // Wait for next frame to ensure canvas is in DOM
  requestAnimationFrame(() => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');

    const chartDatasets = datasets.map(ds => {
      return {
        label: ds.label,
        data: ds.data,
        borderColor: ds.color,
        backgroundColor: options.fill !== false ? (ds.backgroundColor || '#EBE1FB') : 'transparent',
        borderWidth: 2,
        fill: options.fill !== false,
        tension: 0, // sharp brutalist lines
        pointStyle: 'rect',
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBackgroundColor: '#FFB100', // Yellow square boxes
        pointBorderColor: '#000000',
        pointHoverBackgroundColor: '#FFB100',
        pointHoverBorderColor: '#000000',
        pointHoverBorderWidth: 2,
        borderDash: [],
      };
    });

    chartInstances[canvasId] = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets: chartDatasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { 
              font: { family: "'Courier New', monospace" },
              maxRotation: 0,
              maxTicksLimit: 8,
            },
          },
          y: {
            grid: {
              color: '#dcdcdc',
              drawBorder: true,
              borderDash: [2, 4],
            },
            ticks: {
              font: { family: "'Courier New', monospace" },
              callback: (v) => options.dollarFormat ? `$${v.toLocaleString()}` : v.toLocaleString(),
              maxTicksLimit: 5,
            },
            beginAtZero: options.beginAtZero !== false,
          },
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed.y;
                return `${ctx.dataset.label}: ${options.dollarFormat ? '$' + val.toLocaleString() : val.toLocaleString()}`;
              },
              labelColor: (ctx) => {
                return {
                  borderColor: '#000000',
                  backgroundColor: ctx.dataset.borderColor,
                  borderWidth: 2,
                };
              }
            }
          }
        },
        animation: {
          duration: 800,
          easing: 'easeInOutQuart',
        }
      }
    });
  });
}

/**
 * Create a doughnut chart
 */
export function createDoughnutChart(canvasId, labels, data, colors, options = {}) {
  requestAnimationFrame(() => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');

    chartInstances[canvasId] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderColor: '#000000',
          borderWidth: 2,
          hoverBorderColor: '#000000',
          hoverOffset: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '45%', // thicker for brutalism
        plugins: {
          legend: {
            display: true,
            position: 'right',
            labels: {
              padding: 16,
              usePointStyle: true,
              pointStyle: 'rect',
              font: { family: "'Courier New', monospace", size: 14, weight: '700' },
              color: '#000000',
            }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed;
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = ((val / total) * 100).toFixed(1);
                return `${ctx.label}: $${val.toLocaleString()} (${pct}%)`;
              }
            }
          }
        },
        animation: {
          animateRotate: true,
          duration: 800,
          easing: 'easeInOutQuart',
        }
      }
    });
  });
}

/**
 * Create a bar chart
 */
export function createBarChart(canvasId, labels, datasets, options = {}) {
  requestAnimationFrame(() => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    destroyChart(canvasId);

    const ctx = canvas.getContext('2d');

    const chartDatasets = datasets.map(ds => ({
      label: ds.label,
      data: ds.data,
      backgroundColor: ds.color,
      borderColor: '#000000',
      borderWidth: 2,
      borderRadius: 0,
      borderSkipped: false,
      barPercentage: 0.6,
      categoryPercentage: 0.7,
    }));

    chartInstances[canvasId] = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: chartDatasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxRotation: 0 },
          },
          y: {
            grid: {
              color: '#dcdcdc',
              drawBorder: true,
              borderDash: [2, 4],
            },
            ticks: {
              callback: (v) => options.dollarFormat ? `$${v.toLocaleString()}` : v,
              maxTicksLimit: 5,
            },
            beginAtZero: true,
          }
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed.y;
                return `${ctx.dataset.label}: ${options.dollarFormat ? '$' + val.toLocaleString() : val}`;
              }
            }
          }
        },
        animation: {
          duration: 800,
          easing: 'easeInOutQuart',
        }
      }
    });
  });
}

/**
 * Destroy all charts (for page transitions)
 */
export function destroyAllCharts() {
  Object.keys(chartInstances).forEach(id => {
    chartInstances[id].destroy();
  });
  Object.keys(chartInstances).forEach(id => delete chartInstances[id]);
}

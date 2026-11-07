/**
 * Data layer for the dashboard. Everything goes through the Runway API (no direct DB access).
 * If the API is unreachable, fetchers fall back to the mock values in data.js so the UI still renders.
 */
import { metrics as mockMetrics, spendTrend as mockSpendTrend } from '../data.js';

const API = (import.meta.env.VITE_RUNWAY_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const TOKEN = import.meta.env.VITE_RUNWAY_TOKEN || '';

async function get(path, fallback) {
  try {
    const r = await fetch(`${API}${path}`, { headers: TOKEN ? { 'X-Runway-Token': TOKEN } : {} });
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn(`[api] GET ${path} failed (${e.message}); using fallback`);
    return fallback;
  }
}

async function post(path, body) {
  const r = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(TOKEN && { 'X-Runway-Token': TOKEN }) },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`API returned ${r.status}`);
  return r.json();
}

export const fetchRecentTransactions = (limit = 20) => get(`/transactions?limit=${limit}`, []);
export const fetchComplianceTransactions = (limit = 30) => get(`/transactions?pillar=compliance&limit=${limit}`, []);
export const fetchAlerts = (limit = 30) => get(`/alerts?limit=${limit}`, []);
export const fetchPendingAlerts = (limit = 50) => get(`/alerts?pending=true&limit=${limit}`, []);
export const fetchAIUsage = () => get('/ai-usage', []);
export const fetchSubscriptions = () => get('/subscriptions', []);
export const fetchSeatUsage = () => get('/seats', []);
export const fetchPolicyActions = (limit = 10) => get(`/policy-actions?limit=${limit}`, []);
export const fetchEmployees = () => get('/employees', []);
export const fetchNegotiations = () => get('/negotiations', []);

export async function fetchMetrics() {
  return { ...mockMetrics, ...(await get('/dashboard/metrics', {})) };
}

export async function fetchSpendTrend() {
  const trend = await get('/dashboard/spend-trend', null);
  return trend && trend.labels?.length ? trend : mockSpendTrend;
}

export async function askRunway(question) {
  try {
    return (await post('/ask', { question })).answer || 'No answer';
  } catch (e) {
    return `Error: ${e.message}`;
  }
}

/**
 * Send a founder command ("negotiate Cursor", "show pending", "y") exactly as if it were texted.
 * The reply also goes out over the configured notifier (console or iMessage). Returns the reply text.
 */
export async function sendCommand(text) {
  const { reply } = await post('/imessage/inbound', { text });
  return reply || 'Sent ✓';
}

/** Poll for new alerts (replaces Supabase Realtime). Returns an unsubscribe function. */
export function subscribeToAlerts(callback, intervalMs = 5000) {
  let newest = null;
  const tick = async () => {
    const rows = await get('/alerts?limit=10', []);
    const fresh = newest ? rows.filter((a) => a.created_at > newest) : [];
    if (rows.length) newest = rows[0].created_at;
    fresh.reverse().forEach(callback);
  };
  tick();
  const id = setInterval(tick, intervalMs);
  return () => clearInterval(id);
}

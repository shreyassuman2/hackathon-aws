// ============================================================
// RUNWAY DASHBOARD — Mock Data
// Fallback demo data, used when the API is unreachable
// ============================================================

// ── Company ──
export const company = {
  name: 'NovaTech Labs',
  plan: 'Series A',
  employees: 12,
  monthlyBurn: 47200,
};

// ── Employees ──
export const employees = [
  { id: 'e1', name: 'Sarah Chen', role: 'Lead Designer', email: 'sarah@novatech.io', avatar: 'SC' },
  { id: 'e2', name: 'Mike Rodriguez', role: 'Senior Engineer', email: 'mike@novatech.io', avatar: 'MR' },
  { id: 'e3', name: 'Emma Thompson', role: 'Product Manager', email: 'emma@novatech.io', avatar: 'ET' },
  { id: 'e4', name: 'James Park', role: 'Backend Engineer', email: 'james@novatech.io', avatar: 'JP' },
  { id: 'e5', name: 'Priya Sharma', role: 'Data Scientist', email: 'priya@novatech.io', avatar: 'PS' },
];

// ── Transactions (last 30 days) ──
export const transactions = [
  { id: 't1', merchant: 'OpenAI', amount: 4200, category: 'ai_api', date: '2026-04-17', employee: 'e2', status: 'flagged', note: 'GPT-4 batch job — invoice classification' },
  { id: 't2', merchant: 'Anthropic', amount: 2850, category: 'ai_api', date: '2026-04-17', employee: 'e2', status: 'approved', note: 'Claude API usage' },
  { id: 't3', merchant: 'Vercel', amount: 320, category: 'saas', date: '2026-04-16', employee: 'e4', status: 'approved', note: 'Pro plan' },
  { id: 't4', merchant: 'Cursor', amount: 1400, category: 'saas', date: '2026-04-15', employee: 'e2', status: 'flagged', note: '14 seats — 6 dormant' },
  { id: 't5', merchant: 'Notion', amount: 480, category: 'saas', date: '2026-04-15', employee: 'e3', status: 'approved', note: '12 seats team plan' },
  { id: 't6', merchant: 'Figma', amount: 720, category: 'saas', date: '2026-04-14', employee: 'e1', status: 'approved', note: 'Organization plan' },
  { id: 't7', merchant: 'Linear', amount: 240, category: 'saas', date: '2026-04-14', employee: 'e3', status: 'approved', note: 'Standard plan' },
  { id: 't8', merchant: 'Capital Grille', amount: 189, category: 'expense', date: '2026-04-13', employee: 'e1', status: 'approved', note: 'Client dinner — Acme/Mike Chen' },
  { id: 't9', merchant: 'Uber', amount: 47, category: 'expense', date: '2026-04-13', employee: 'e3', status: 'approved', note: 'Office → client meeting' },
  { id: 't10', merchant: 'Amazon Web Services', amount: 890, category: 'saas', date: '2026-04-12', employee: 'e4', status: 'approved', note: 'Infrastructure' },
  { id: 't11', merchant: 'Midjourney', amount: 200, category: 'saas', date: '2026-04-12', employee: 'e1', status: 'flagged', note: '21 days unused' },
  { id: 't12', merchant: 'GitHub', amount: 252, category: 'saas', date: '2026-04-11', employee: 'e2', status: 'approved', note: 'Team plan' },
  { id: 't13', merchant: 'Supabase', amount: 150, category: 'saas', date: '2026-04-10', employee: 'e4', status: 'approved', note: 'Pro plan' },
  { id: 't14', merchant: 'DoorDash', amount: 62, category: 'expense', date: '2026-04-10', employee: 'e5', status: 'pending', note: 'Team lunch order' },
  { id: 't15', merchant: 'WeWork', amount: 3200, category: 'expense', date: '2026-04-09', employee: 'e3', status: 'approved', note: 'Monthly office space' },
];

// ── Subscriptions ──
export const subscriptions = [
  { id: 's1', vendor: 'Cursor', seatsPaid: 14, seatsActive: 8, monthlyCost: 1400, renewal: '2026-04-21', status: 'critical', utilization: 57, category: 'dev-tools' },
  { id: 's2', vendor: 'Notion', seatsPaid: 12, seatsActive: 10, monthlyCost: 480, renewal: '2026-05-01', status: 'healthy', utilization: 83, category: 'productivity' },
  { id: 's3', vendor: 'Figma', seatsPaid: 8, seatsActive: 5, monthlyCost: 720, renewal: '2026-05-15', status: 'warning', utilization: 63, category: 'design' },
  { id: 's4', vendor: 'Linear', seatsPaid: 12, seatsActive: 11, monthlyCost: 240, renewal: '2026-06-01', status: 'healthy', utilization: 92, category: 'productivity' },
  { id: 's5', vendor: 'Vercel', seatsPaid: 5, seatsActive: 4, monthlyCost: 320, renewal: '2026-05-10', status: 'healthy', utilization: 80, category: 'infrastructure' },
  { id: 's6', vendor: 'GitHub', seatsPaid: 12, seatsActive: 12, monthlyCost: 252, renewal: '2026-06-15', status: 'healthy', utilization: 100, category: 'dev-tools' },
  { id: 's7', vendor: 'Midjourney', seatsPaid: 3, seatsActive: 0, monthlyCost: 200, renewal: '2026-04-25', status: 'critical', utilization: 0, category: 'design' },
  { id: 's8', vendor: 'AWS', seatsPaid: null, seatsActive: null, monthlyCost: 890, renewal: null, status: 'healthy', utilization: null, category: 'infrastructure' },
  { id: 's9', vendor: 'Supabase', seatsPaid: null, seatsActive: null, monthlyCost: 150, renewal: '2026-05-20', status: 'healthy', utilization: null, category: 'infrastructure' },
  { id: 's10', vendor: 'Slack', seatsPaid: 12, seatsActive: 9, monthlyCost: 180, renewal: '2026-05-05', status: 'warning', utilization: 75, category: 'communication' },
  { id: 's11', vendor: 'Loom', seatsPaid: 8, seatsActive: 2, monthlyCost: 150, renewal: '2026-04-28', status: 'critical', utilization: 25, category: 'communication' },
  { id: 's12', vendor: '1Password', seatsPaid: 12, seatsActive: 12, monthlyCost: 96, renewal: '2026-07-01', status: 'healthy', utilization: 100, category: 'security' },
];

// ── AI Usage Events (aggregated by model) ──
export const aiUsage = [
  { model: 'GPT-4', provider: 'OpenAI', calls: 38420, inputTokens: 12400000, outputTokens: 6200000, cost: 3420, recommendedModel: 'Claude Haiku', potentialSavings: 2840, confidence: 0.94, pattern: 'Invoice classification' },
  { model: 'Claude Sonnet 4.5', provider: 'Anthropic', calls: 8200, inputTokens: 4100000, outputTokens: 2050000, cost: 1890, recommendedModel: null, potentialSavings: 0, confidence: 1.0, pattern: 'Complex reasoning tasks' },
  { model: 'GPT-4', provider: 'OpenAI', calls: 2100, inputTokens: 840000, outputTokens: 420000, cost: 780, recommendedModel: 'Gemini Flash', potentialSavings: 620, confidence: 0.88, pattern: 'Data extraction from PDFs' },
  { model: 'Claude Haiku 4.5', provider: 'Anthropic', calls: 15600, inputTokens: 3900000, outputTokens: 1560000, cost: 340, recommendedModel: null, potentialSavings: 0, confidence: 1.0, pattern: 'Classification & routing' },
  { model: 'GPT-3.5-Turbo', provider: 'OpenAI', calls: 45000, inputTokens: 9000000, outputTokens: 4500000, cost: 620, recommendedModel: null, potentialSavings: 0, confidence: 1.0, pattern: 'Simple text generation' },
  { model: 'Gemini 2.5 Flash', provider: 'Google', calls: 3200, inputTokens: 1600000, outputTokens: 800000, cost: 180, recommendedModel: null, potentialSavings: 0, confidence: 1.0, pattern: 'OCR & document parsing' },
];

// ── Spend Trend (30 days) ──
export const spendTrend = {
  labels: ['Mar 18', 'Mar 20', 'Mar 22', 'Mar 24', 'Mar 26', 'Mar 28', 'Mar 30', 'Apr 1', 'Apr 3', 'Apr 5', 'Apr 7', 'Apr 9', 'Apr 11', 'Apr 13', 'Apr 15', 'Apr 17'],
  datasets: {
    total: [1200, 1450, 1380, 1600, 1520, 1780, 1650, 2100, 1900, 2340, 2200, 2580, 2800, 3100, 2950, 3400],
    ai: [400, 520, 480, 640, 580, 720, 650, 890, 780, 1100, 960, 1240, 1380, 1560, 1480, 1700],
    saas: [600, 680, 650, 710, 700, 780, 740, 850, 820, 880, 860, 920, 980, 1050, 1020, 1100],
    expenses: [200, 250, 250, 250, 240, 280, 260, 360, 300, 360, 380, 420, 440, 490, 450, 600],
  }
};

// ── AI Spend Trend (daily, by provider) ──
export const aiSpendTrend = {
  labels: ['Apr 1', 'Apr 3', 'Apr 5', 'Apr 7', 'Apr 9', 'Apr 11', 'Apr 13', 'Apr 15', 'Apr 17'],
  datasets: {
    openai: [280, 310, 420, 380, 490, 520, 580, 640, 700],
    anthropic: [150, 180, 200, 220, 240, 260, 280, 300, 340],
    google: [20, 25, 30, 28, 35, 40, 38, 45, 50],
  }
};

// ── Compliance / Expense data ──
export const expenses = [
  { id: 'x1', employee: 'e1', merchant: 'Capital Grille', amount: 189, date: '2026-04-13', category: 'Meals & Entertainment', status: 'approved', policyCheck: 'pass', reason: 'Client dinner with Acme Corp — Mike Chen' },
  { id: 'x2', employee: 'e3', merchant: 'Uber', amount: 47, date: '2026-04-13', category: 'Transportation', status: 'approved', policyCheck: 'pass', reason: 'Office to client meeting' },
  { id: 'x3', employee: 'e5', merchant: 'DoorDash', amount: 62, date: '2026-04-10', category: 'Meals & Entertainment', status: 'pending', policyCheck: 'review', reason: 'Team lunch — no receipt attached' },
  { id: 'x4', employee: 'e3', merchant: 'WeWork', amount: 3200, date: '2026-04-09', category: 'Office', status: 'approved', policyCheck: 'pass', reason: 'Monthly co-working space' },
  { id: 'x5', employee: 'e2', merchant: 'Best Buy', amount: 1299, date: '2026-04-08', category: 'Equipment', status: 'flagged', policyCheck: 'fail', reason: 'Monitor purchase — exceeds $500 limit without pre-approval' },
  { id: 'x6', employee: 'e1', merchant: 'Delta Airlines', amount: 480, date: '2026-04-07', category: 'Travel', status: 'approved', policyCheck: 'pass', reason: 'NYC → SF business trip' },
  { id: 'x7', employee: 'e4', merchant: 'Amazon', amount: 89, date: '2026-04-06', category: 'Supplies', status: 'approved', policyCheck: 'pass', reason: 'Office supplies — keyboard, cables' },
  { id: 'x8', employee: 'e2', merchant: 'Starbucks', amount: 34, date: '2026-04-05', category: 'Meals & Entertainment', status: 'approved', policyCheck: 'pass', reason: 'Team coffee meeting' },
  { id: 'x9', employee: 'e5', merchant: 'Coursera', amount: 199, date: '2026-04-04', category: 'Education', status: 'pending', policyCheck: 'review', reason: 'ML course — needs manager approval for education expenses' },
  { id: 'x10', employee: 'e1', merchant: 'Apple Store', amount: 2499, date: '2026-04-03', category: 'Equipment', status: 'flagged', policyCheck: 'fail', reason: 'MacBook purchase — no PO number, exceeds policy limit' },
];

// ── Calculated metrics ──
export const metrics = {
  totalMonthlySpend: 47200,
  identifiedSavings: 8340,
  activeSubscriptions: 24,
  ghostSeats: 11,
  complianceFlags: 3,
  pendingReview: 2,
  totalAISpend: 7230,
  aiPotentialSavings: 3460,
  wrongModelCalls: 40520,
  avgCostPerCall: 0.064,
  totalSaaSSpend: 5078,
  zombieSubscriptions: 2,
  upcomingRenewals: 4,
  totalExpenses: 8098,
  autoApproved: 6,
  flagged: 2,
  pendingExpenses: 2,
};

// ── Activity Feed ──
export const activities = [
  { type: 'alert', icon: '🚨', color: 'red', text: '<strong>OpenAI bill spike</strong> — $4,200 this week, up 340% from last week. Batch job running GPT-4 on invoice classification.', time: '2 hours ago', amount: '-$4,200' },
  { type: 'savings', icon: '💰', color: 'green', text: '<strong>Savings identified:</strong> Route invoice classification to Haiku at 94% parity.', time: '2 hours ago', amount: '+$2,840/mo' },
  { type: 'ghost', icon: '👻', color: 'purple', text: '<strong>Ghost seats found</strong> — Cursor: 6 of 14 seats unused for 30+ days. Recommend downgrade.', time: '5 hours ago', amount: '+$600/mo' },
  { type: 'compliance', icon: '⚠️', color: 'orange', text: '<strong>Expense flagged:</strong> Mike R. — $1,299 Best Buy purchase exceeds policy limit.', time: '8 hours ago', amount: '$1,299' },
  { type: 'approved', icon: '✅', color: 'green', text: '<strong>Auto-approved:</strong> Sarah C. — $189 Capital Grille, client dinner (Acme/Mike Chen). Policy ✓', time: '1 day ago', amount: '$189' },
  { type: 'renewal', icon: '⏰', color: 'blue', text: '<strong>Renewal in 4 days:</strong> Cursor — $1,400/mo. Usage audit recommends downgrading to 8 seats.', time: '1 day ago', amount: '$1,400/mo' },
  { type: 'zombie', icon: '🧟', color: 'red', text: '<strong>Zombie subscription:</strong> Midjourney — $200/mo, 0 active users in 21 days. Cancellation recommended.', time: '2 days ago', amount: '+$200/mo' },
];

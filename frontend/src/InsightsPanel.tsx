import { useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  ComposedChart,
} from 'recharts';
import type { Insights } from './types';

const COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#a855f7', '#14b8a6', '#f97316'];

function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '-';
  return n.toLocaleString();
}

function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatMinute(minute: string): string {
  const d = new Date(minute);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function InsightsPanel({ insights }: { insights: Insights | null }) {
  const timeSeries = useMemo(
    () =>
      (insights?.time_series || []).map((p) => ({
        ...p,
        label: formatMinute(p.minute),
      })),
    [insights?.time_series]
  );

  const latencyHistogram = useMemo(
    () => insights?.latency?.histogram || [],
    [insights?.latency?.histogram]
  );

  const topSlow = useMemo(() => insights?.latency?.top_slow || [], [insights?.latency?.top_slow]);

  const modelBreakdown = useMemo(
    () => insights?.model_breakdown || [],
    [insights?.model_breakdown]
  );

  const stopReasonData = useMemo(
    () =>
      Object.entries(insights?.stop_reason_distribution || {}).map(([name, value]) => ({
        name,
        value,
      })),
    [insights?.stop_reason_distribution]
  );

  const streamingData = useMemo(
    () =>
      Object.entries(insights?.streaming_ratio || {}).map(([name, value]) => ({
        name,
        value,
      })),
    [insights?.streaming_ratio]
  );

  if (!insights) return null;

  const te = insights.token_efficiency;
  const cost = insights.cost_estimate;
  const rbs = insights.request_body_stats;

  return (
    <div className="insights-panel">
      <h2 className="insights-title">Insights</h2>

      {/* Time series */}
      <div className="charts-grid">
        <div className="chart-card wide">
          <h3>Requests / Error per Minute</h3>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={timeSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="label" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                <Legend />
                <Line type="monotone" dataKey="total_requests" name="Requests" stroke="#22c55e" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="error_count" name="Errors" stroke="#ef4444" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card wide">
          <h3>Tokens per Minute</h3>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={timeSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="label" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <YAxis stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                <Legend />
                <Bar dataKey="total_input_tokens" name="Input Tokens" stackId="a" fill="#3b82f6" />
                <Bar dataKey="total_output_tokens" name="Output Tokens" stackId="a" fill="#22c55e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Latency */}
      <div className="insights-section">
        <h3>Latency</h3>
        <div className="metrics latency-metrics">
          <div className="metric-card">
            <h3>P50 Duration</h3>
            <div className="value">{formatDuration(insights.latency.p50_duration_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>P95 Duration</h3>
            <div className="value">{formatDuration(insights.latency.p95_duration_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>P99 Duration</h3>
            <div className="value">{formatDuration(insights.latency.p99_duration_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>P50 TTFB</h3>
            <div className="value">{formatDuration(insights.latency.p50_ttfb_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>P95 TTFB</h3>
            <div className="value">{formatDuration(insights.latency.p95_ttfb_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>P99 TTFB</h3>
            <div className="value">{formatDuration(insights.latency.p99_ttfb_ms)}</div>
          </div>
        </div>

        <div className="charts-grid">
          <div className="chart-card">
            <h3>Duration Distribution</h3>
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={latencyHistogram}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="bucket" stroke="#94a3b8" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                  <Bar dataKey="count" fill="#3b82f6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="chart-card">
            <h3>Top 5 Slowest Requests</h3>
            <div className="top-slow-table-wrapper">
              <table className="top-slow-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Model</th>
                    <th>Duration</th>
                    <th>TTFB</th>
                  </tr>
                </thead>
                <tbody>
                  {topSlow.map((req) => (
                    <tr key={req.id}>
                      <td title={req.id}>{req.id.slice(-12)}</td>
                      <td>{req.model || '-'}</td>
                      <td>{formatDuration(req.duration_ms)}</td>
                      <td>{formatDuration(req.ttfb_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Model breakdown */}
      <div className="insights-section">
        <h3>Model Breakdown</h3>
        <div className="chart-card">
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={modelBreakdown}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="model" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <YAxis yAxisId="left" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <YAxis yAxisId="right" orientation="right" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                <Legend />
                <Bar yAxisId="left" dataKey="count" name="Requests" fill="#22c55e" />
                <Bar yAxisId="left" dataKey="total_tokens" name="Total Tokens" fill="#3b82f6" />
                <Line yAxisId="right" type="monotone" dataKey="avg_duration_ms" name="Avg Duration (ms)" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Distributions */}
      <div className="charts-grid">
        <div className="chart-card">
          <h3>Stop Reason</h3>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie data={stopReasonData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {stopReasonData.map((_, idx) => (
                    <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card">
          <h3>Streaming vs Non-streaming</h3>
          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie data={streamingData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {streamingData.map((_, idx) => (
                    <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Token efficiency & cost */}
      <div className="insights-section">
        <h3>Token Efficiency & Cost</h3>
        <div className="metrics">
          <div className="metric-card">
            <h3>Output / Input Ratio</h3>
            <div className="value">{te.output_input_ratio?.toFixed(2) ?? '-'}</div>
          </div>
          <div className="metric-card">
            <h3>Output Tokens / Second</h3>
            <div className="value">{formatNumber(te.tokens_per_second)}</div>
          </div>
          <div className="metric-card">
            <h3>Cache Hit Rate</h3>
            <div className="value">{(te.cache_hit_rate * 100).toFixed(1)}%</div>
          </div>
          <div className="metric-card">
            <h3>Cache Read Tokens</h3>
            <div className="value">{formatNumber(te.cache_read_input_tokens)}</div>
          </div>
          <div className="metric-card">
            <h3>Estimated Cost</h3>
            <div className="value">${cost.total_cost.toFixed(4)}</div>
          </div>
        </div>

        <div className="cost-by-model">
          <h4>Cost by Model</h4>
          <div className="cost-cards">
            {Object.entries(cost.by_model).map(([model, c]) => (
              <div className="cost-card" key={model}>
                <div className="cost-model">{model}</div>
                <div className="cost-value">${c.total_cost.toFixed(4)}</div>
                <div className="cost-detail">in ${c.input_cost.toFixed(4)} / out ${c.output_cost.toFixed(4)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Request body stats */}
      <div className="insights-section">
        <h3>Request Body Stats (/v1/messages)</h3>
        <div className="metrics">
          <div className="metric-card">
            <h3>Avg Messages</h3>
            <div className="value">{rbs.avg_messages_count.toFixed(1)}</div>
          </div>
          <div className="metric-card">
            <h3>Max Messages</h3>
            <div className="value">{formatNumber(rbs.max_messages_count)}</div>
          </div>
          <div className="metric-card">
            <h3>Avg System Length</h3>
            <div className="value">{formatNumber(rbs.avg_system_length)}</div>
          </div>
          <div className="metric-card">
            <h3>Avg User Content</h3>
            <div className="value">{formatNumber(rbs.avg_user_content_length)}</div>
          </div>
        </div>

        <div className="charts-grid">
          <div className="chart-card">
            <h3>Tool Count Distribution</h3>
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={Object.entries(rbs.tool_count_distribution).map(([k, v]) => ({ tools: k, count: v }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="tools" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                  <Bar dataKey="count" fill="#a855f7" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="chart-card">
            <h3>Max Tokens Distribution</h3>
            <div className="chart-wrapper">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={Object.entries(rbs.max_tokens_distribution).map(([k, v]) => ({ range: k, count: v }))}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="range" stroke="#94a3b8" tick={{ fontSize: 11 }} angle={-15} textAnchor="end" />
                  <YAxis stroke="#94a3b8" tick={{ fontSize: 12 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
                  <Bar dataKey="count" fill="#f59e0b" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

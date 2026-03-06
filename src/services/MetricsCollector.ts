/**
 * Metrics Collector
 * Collects and aggregates historical metrics for monitoring and analysis
 */

import { Database } from 'bun:sqlite';
import path from 'path';

export interface Metric {
  name: string;
  value: number;
  tags?: Record<string, string>;
  timestamp: string;
}

export interface AggregatedMetric {
  name: string;
  period: 'hour' | 'day' | 'week' | 'month';
  startTime: string;
  endTime: string;
  count: number;
  sum: number;
  avg: number;
  min: number;
  max: number;
  tags?: Record<string, string>;
}

export interface MetricSeries {
  name: string;
  dataPoints: Array<{ timestamp: string; value: number }>;
}

export class MetricsCollector {
  private db: Database;
  private metricsBuffer: Metric[];
  private bufferSize: number;
  private flushInterval: number;
  private flushTimer?: Timer;

  constructor(
    dbPath: string = './output/archive.db',
    bufferSize: number = 100,
    flushIntervalMs: number = 10000
  ) {
    const fullPath = path.resolve(dbPath);
    this.db = new Database(fullPath);
    this.metricsBuffer = [];
    this.bufferSize = bufferSize;
    this.flushInterval = flushIntervalMs;
    this.initializeMetricsTable();
  }

  /**
   * Initialize metrics table if it doesn't exist
   */
  private initializeMetricsTable(): void {
    try {
      this.db.exec(`
        CREATE TABLE IF NOT EXISTS metrics (
          metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          value REAL NOT NULL,
          tags TEXT,
          timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_metrics_name_time
        ON metrics(name, timestamp);

        CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
        ON metrics(timestamp);
      `);
    } catch (error) {
      console.error('[MetricsCollector] Failed to initialize metrics table:', error);
    }
  }

  /**
   * Record a metric
   */
  record(name: string, value: number, tags?: Record<string, string>): void {
    const metric: Metric = {
      name,
      value,
      tags,
      timestamp: new Date().toISOString()
    };

    this.metricsBuffer.push(metric);

    // Auto-flush if buffer is full
    if (this.metricsBuffer.length >= this.bufferSize) {
      this.flush();
    }
  }

  /**
   * Record multiple metrics at once
   */
  recordBatch(metrics: Array<{ name: string; value: number; tags?: Record<string, string> }>): void {
    const timestamp = new Date().toISOString();

    for (const m of metrics) {
      this.metricsBuffer.push({
        ...m,
        timestamp
      });
    }

    if (this.metricsBuffer.length >= this.bufferSize) {
      this.flush();
    }
  }

  /**
   * Increment a counter metric
   */
  increment(name: string, delta: number = 1, tags?: Record<string, string>): void {
    this.record(name, delta, tags);
  }

  /**
   * Record a timing metric (in milliseconds)
   */
  timing(name: string, durationMs: number, tags?: Record<string, string>): void {
    this.record(name, durationMs, tags);
  }

  /**
   * Record a gauge (current value)
   */
  gauge(name: string, value: number, tags?: Record<string, string>): void {
    this.record(name, value, tags);
  }

  /**
   * Flush buffered metrics to database
   */
  flush(): void {
    if (this.metricsBuffer.length === 0) {
      return;
    }

    try {
      const stmt = this.db.prepare(`
        INSERT INTO metrics (name, value, tags, timestamp)
        VALUES (?, ?, ?, ?)
      `);

      for (const metric of this.metricsBuffer) {
        stmt.run(
          metric.name,
          metric.value,
          metric.tags ? JSON.stringify(metric.tags) : null,
          metric.timestamp
        );
      }

      console.log(`[MetricsCollector] Flushed ${this.metricsBuffer.length} metrics`);
      this.metricsBuffer = [];
    } catch (error) {
      console.error('[MetricsCollector] Failed to flush metrics:', error);
    }
  }

  /**
   * Start automatic flushing
   */
  startAutoFlush(): void {
    if (this.flushTimer) {
      console.warn('[MetricsCollector] Auto-flush already running');
      return;
    }

    console.log(`[MetricsCollector] Starting auto-flush (interval: ${this.flushInterval}ms)`);

    this.flushTimer = setInterval(() => {
      this.flush();
    }, this.flushInterval);
  }

  /**
   * Stop automatic flushing
   */
  stopAutoFlush(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = undefined;
      this.flush(); // Final flush
      console.log('[MetricsCollector] Stopped auto-flush');
    }
  }

  /**
   * Get raw metrics for a time range
   */
  getMetrics(
    name: string,
    startTime: string,
    endTime: string,
    tags?: Record<string, string>
  ): Metric[] {
    try {
      let query = `
        SELECT name, value, tags, timestamp
        FROM metrics
        WHERE name = ? AND timestamp >= ? AND timestamp <= ?
      `;

      const params: any[] = [name, startTime, endTime];

      if (tags) {
        // Filter by tags (simplified - checks if all tags match)
        query += ` AND tags LIKE ?`;
        params.push(`%${JSON.stringify(tags)}%`);
      }

      query += ` ORDER BY timestamp ASC`;

      const rows = this.db.prepare(query).all(...params) as any[];

      return rows.map(row => ({
        name: row.name,
        value: row.value,
        tags: row.tags ? JSON.parse(row.tags) : undefined,
        timestamp: row.timestamp
      }));
    } catch (error) {
      console.error('[MetricsCollector] Failed to get metrics:', error);
      return [];
    }
  }

  /**
   * Get aggregated metrics for a time range
   */
  getAggregatedMetrics(
    name: string,
    startTime: string,
    endTime: string,
    period: AggregatedMetric['period'] = 'hour'
  ): AggregatedMetric[] {
    try {
      // SQLite doesn't have native date truncation, so we'll aggregate in-memory
      const metrics = this.getMetrics(name, startTime, endTime);

      if (metrics.length === 0) {
        return [];
      }

      // Group by period
      const groups = new Map<string, Metric[]>();
      const periodMs = this.getPeriodMs(period);

      for (const metric of metrics) {
        const timestamp = new Date(metric.timestamp).getTime();
        const periodStart = Math.floor(timestamp / periodMs) * periodMs;
        const periodKey = new Date(periodStart).toISOString();

        if (!groups.has(periodKey)) {
          groups.set(periodKey, []);
        }
        groups.get(periodKey)!.push(metric);
      }

      // Aggregate each group
      const aggregated: AggregatedMetric[] = [];

      for (const [periodKey, groupMetrics] of groups) {
        const values = groupMetrics.map(m => m.value);
        const periodStart = new Date(periodKey);
        const periodEnd = new Date(periodStart.getTime() + periodMs);

        aggregated.push({
          name,
          period,
          startTime: periodStart.toISOString(),
          endTime: periodEnd.toISOString(),
          count: values.length,
          sum: values.reduce((a, b) => a + b, 0),
          avg: values.reduce((a, b) => a + b, 0) / values.length,
          min: Math.min(...values),
          max: Math.max(...values)
        });
      }

      return aggregated.sort((a, b) => a.startTime.localeCompare(b.startTime));
    } catch (error) {
      console.error('[MetricsCollector] Failed to get aggregated metrics:', error);
      return [];
    }
  }

  /**
   * Get metric series for charting
   */
  getMetricSeries(
    name: string,
    startTime: string,
    endTime: string,
    maxPoints: number = 100
  ): MetricSeries {
    try {
      const metrics = this.getMetrics(name, startTime, endTime);

      // Downsample if too many points
      let dataPoints = metrics.map(m => ({
        timestamp: m.timestamp,
        value: m.value
      }));

      if (dataPoints.length > maxPoints) {
        const step = Math.ceil(dataPoints.length / maxPoints);
        dataPoints = dataPoints.filter((_, i) => i % step === 0);
      }

      return {
        name,
        dataPoints
      };
    } catch (error) {
      console.error('[MetricsCollector] Failed to get metric series:', error);
      return { name, dataPoints: [] };
    }
  }

  /**
   * Get metric statistics for a time range
   */
  getStatistics(name: string, startTime: string, endTime: string): {
    count: number;
    sum: number;
    avg: number;
    min: number;
    max: number;
    p50: number;
    p95: number;
    p99: number;
  } | null {
    try {
      const metrics = this.getMetrics(name, startTime, endTime);

      if (metrics.length === 0) {
        return null;
      }

      const values = metrics.map(m => m.value).sort((a, b) => a - b);

      return {
        count: values.length,
        sum: values.reduce((a, b) => a + b, 0),
        avg: values.reduce((a, b) => a + b, 0) / values.length,
        min: values[0],
        max: values[values.length - 1],
        p50: this.percentile(values, 50),
        p95: this.percentile(values, 95),
        p99: this.percentile(values, 99)
      };
    } catch (error) {
      console.error('[MetricsCollector] Failed to get statistics:', error);
      return null;
    }
  }

  /**
   * Calculate percentile
   */
  private percentile(sortedValues: number[], p: number): number {
    const index = (p / 100) * (sortedValues.length - 1);
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    const weight = index - lower;

    return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
  }

  /**
   * Get period duration in milliseconds
   */
  private getPeriodMs(period: AggregatedMetric['period']): number {
    switch (period) {
      case 'hour':
        return 60 * 60 * 1000;
      case 'day':
        return 24 * 60 * 60 * 1000;
      case 'week':
        return 7 * 24 * 60 * 60 * 1000;
      case 'month':
        return 30 * 24 * 60 * 60 * 1000;
      default:
        return 60 * 60 * 1000;
    }
  }

  /**
   * Clean up old metrics
   */
  cleanup(olderThanDays: number = 30): number {
    try {
      const cutoff = new Date(Date.now() - olderThanDays * 24 * 60 * 60 * 1000).toISOString();

      const result = this.db.prepare(`
        DELETE FROM metrics
        WHERE timestamp < ?
      `).run(cutoff);

      if (result.changes > 0) {
        console.log(`[MetricsCollector] Cleaned up ${result.changes} old metrics`);
      }

      return result.changes;
    } catch (error) {
      console.error('[MetricsCollector] Failed to cleanup metrics:', error);
      return 0;
    }
  }

  /**
   * Get list of all metric names
   */
  getMetricNames(): string[] {
    try {
      const rows = this.db.prepare(`
        SELECT DISTINCT name FROM metrics ORDER BY name
      `).all() as Array<{ name: string }>;

      return rows.map(r => r.name);
    } catch (error) {
      console.error('[MetricsCollector] Failed to get metric names:', error);
      return [];
    }
  }

  /**
   * Close and cleanup
   */
  close(): void {
    this.stopAutoFlush();
    this.db.close();
  }
}

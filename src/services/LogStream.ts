/**
 * LogStream - Captures console logs and streams them to clients
 * Uses Server-Sent Events (SSE) for real-time log delivery
 */

import { Response } from 'express';

interface LogEntry {
  timestamp: string;
  level: 'log' | 'info' | 'warn' | 'error';
  message: string;
}

class LogStream {
  private clients: Set<Response>;
  private logBuffer: LogEntry[];
  private maxBufferSize: number;
  private originalConsole: {
    log: typeof console.log;
    info: typeof console.info;
    warn: typeof console.warn;
    error: typeof console.error;
  };

  constructor(maxBufferSize: number = 1000) {
    this.clients = new Set();
    this.logBuffer = [];
    this.maxBufferSize = maxBufferSize;

    // Store original console methods
    this.originalConsole = {
      log: console.log,
      info: console.info,
      warn: console.warn,
      error: console.error
    };

    // Intercept console methods
    this.interceptConsole();
  }

  /**
   * Intercept console methods to capture logs
   */
  private interceptConsole(): void {
    const self = this;

    console.log = function(...args: any[]) {
      self.addLog('log', args.join(' '));
      self.originalConsole.log.apply(console, args);
    };

    console.info = function(...args: any[]) {
      self.addLog('info', args.join(' '));
      self.originalConsole.info.apply(console, args);
    };

    console.warn = function(...args: any[]) {
      self.addLog('warn', args.join(' '));
      self.originalConsole.warn.apply(console, args);
    };

    console.error = function(...args: any[]) {
      self.addLog('error', args.join(' '));
      self.originalConsole.error.apply(console, args);
    };
  }

  /**
   * Add a log entry
   */
  private addLog(level: LogEntry['level'], message: string): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message
    };

    // Add to buffer
    this.logBuffer.push(entry);

    // Trim buffer if needed
    if (this.logBuffer.length > this.maxBufferSize) {
      this.logBuffer.shift();
    }

    // Broadcast to all connected clients
    this.broadcast(entry);
  }

  /**
   * Broadcast a log entry to all connected clients
   */
  private broadcast(entry: LogEntry): void {
    const data = JSON.stringify(entry);

    this.clients.forEach(client => {
      try {
        client.write(`data: ${data}\n\n`);
      } catch (error) {
        // Client disconnected, remove it
        this.clients.delete(client);
      }
    });
  }

  /**
   * Register a new SSE client
   */
  addClient(res: Response): void {
    // Set SSE headers
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no'); // Disable nginx buffering

    // Send initial buffer (last N logs)
    const recentLogs = this.logBuffer.slice(-100); // Send last 100 logs
    recentLogs.forEach(entry => {
      res.write(`data: ${JSON.stringify(entry)}\n\n`);
    });

    // Add client to set
    this.clients.add(res);

    // Remove client on disconnect
    res.on('close', () => {
      this.clients.delete(res);
    });
  }

  /**
   * Get recent logs (for initial load or polling fallback)
   */
  getRecentLogs(count: number = 100): LogEntry[] {
    return this.logBuffer.slice(-count);
  }

  /**
   * Clear log buffer
   */
  clearLogs(): void {
    this.logBuffer = [];
  }

  /**
   * Get number of connected clients
   */
  getClientCount(): number {
    return this.clients.size;
  }
}

// Export singleton instance
export const logStream = new LogStream();

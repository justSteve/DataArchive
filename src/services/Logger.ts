/**
 * Structured Logger
 * Provides structured logging with optional Winston integration
 * Falls back to console logging if Winston is not available
 */

export interface LogContext {
  [key: string]: any;
}

export interface LoggerOptions {
  level: 'debug' | 'info' | 'warn' | 'error';
  enableConsole: boolean;
  enableFile: boolean;
  logDir: string;
  maxFiles: number;
  maxFileSize: string;
}

const DEFAULT_OPTIONS: LoggerOptions = {
  level: 'info',
  enableConsole: true,
  enableFile: true,
  logDir: './logs',
  maxFiles: 14, // 2 weeks
  maxFileSize: '20m'
};

/**
 * Structured Logger
 *
 * Usage:
 * const logger = new Logger('ServiceName');
 * logger.info('Operation completed', { duration: 123, count: 456 });
 * logger.error('Operation failed', { error: err.message }, err);
 */
export class Logger {
  private name: string;
  private options: LoggerOptions;
  private winstonLogger?: any; // Winston logger instance if available

  constructor(name: string, options: Partial<LoggerOptions> = {}) {
    this.name = name;
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.initializeWinston();
  }

  /**
   * Try to initialize Winston if available
   */
  private initializeWinston(): void {
    try {
      // Try to load Winston (may not be installed)
      const winston = require('winston');

      const transports: any[] = [];

      // Console transport
      if (this.options.enableConsole) {
        transports.push(
          new winston.transports.Console({
            format: winston.format.combine(
              winston.format.colorize(),
              winston.format.timestamp(),
              winston.format.printf((info: any) => {
                const { timestamp, level, message, ...meta } = info;
                const metaStr = Object.keys(meta).length > 0 ? ` ${JSON.stringify(meta)}` : '';
                return `${timestamp} [${this.name}] ${level}: ${message}${metaStr}`;
              })
            )
          })
        );
      }

      // File transports
      if (this.options.enableFile) {
        transports.push(
          new winston.transports.File({
            filename: `${this.options.logDir}/error.log`,
            level: 'error',
            maxsize: this.parseFileSize(this.options.maxFileSize),
            maxFiles: this.options.maxFiles,
            format: winston.format.combine(
              winston.format.timestamp(),
              winston.format.json()
            )
          })
        );

        transports.push(
          new winston.transports.File({
            filename: `${this.options.logDir}/combined.log`,
            maxsize: this.parseFileSize(this.options.maxFileSize),
            maxFiles: this.options.maxFiles,
            format: winston.format.combine(
              winston.format.timestamp(),
              winston.format.json()
            )
          })
        );
      }

      this.winstonLogger = winston.createLogger({
        level: this.options.level,
        transports
      });

      console.log(`[Logger] Initialized Winston logger for ${this.name}`);
    } catch (error) {
      console.log(`[Logger] Winston not available, using console fallback for ${this.name}`);
      this.winstonLogger = null;
    }
  }

  /**
   * Parse file size string to bytes
   */
  private parseFileSize(sizeStr: string): number {
    const units: Record<string, number> = {
      b: 1,
      k: 1024,
      m: 1024 * 1024,
      g: 1024 * 1024 * 1024
    };

    const match = sizeStr.toLowerCase().match(/^(\d+)([bkmg]?)$/);
    if (!match) return 20 * 1024 * 1024; // Default 20MB

    const value = parseInt(match[1]);
    const unit = match[2] || 'b';
    return value * (units[unit] || 1);
  }

  /**
   * Format log message with context
   */
  private formatMessage(message: string, context?: LogContext): string {
    if (!context || Object.keys(context).length === 0) {
      return message;
    }
    return `${message} ${JSON.stringify(context)}`;
  }

  /**
   * Log debug message
   */
  debug(message: string, context?: LogContext): void {
    if (this.winstonLogger) {
      this.winstonLogger.debug(message, context || {});
    } else {
      console.debug(`[${this.name}] DEBUG: ${this.formatMessage(message, context)}`);
    }
  }

  /**
   * Log info message
   */
  info(message: string, context?: LogContext): void {
    if (this.winstonLogger) {
      this.winstonLogger.info(message, context || {});
    } else {
      console.info(`[${this.name}] INFO: ${this.formatMessage(message, context)}`);
    }
  }

  /**
   * Log warning message
   */
  warn(message: string, context?: LogContext): void {
    if (this.winstonLogger) {
      this.winstonLogger.warn(message, context || {});
    } else {
      console.warn(`[${this.name}] WARN: ${this.formatMessage(message, context)}`);
    }
  }

  /**
   * Log error message
   */
  error(message: string, context?: LogContext, error?: Error): void {
    const errorContext = {
      ...context,
      ...(error && {
        error: {
          message: error.message,
          stack: error.stack,
          name: error.name
        }
      })
    };

    if (this.winstonLogger) {
      this.winstonLogger.error(message, errorContext);
    } else {
      console.error(`[${this.name}] ERROR: ${this.formatMessage(message, errorContext)}`);
      if (error) {
        console.error(error);
      }
    }
  }

  /**
   * Log with custom level
   */
  log(level: LoggerOptions['level'], message: string, context?: LogContext): void {
    switch (level) {
      case 'debug':
        this.debug(message, context);
        break;
      case 'info':
        this.info(message, context);
        break;
      case 'warn':
        this.warn(message, context);
        break;
      case 'error':
        this.error(message, context);
        break;
    }
  }

  /**
   * Create child logger with additional context
   */
  child(childName: string, defaultContext?: LogContext): Logger {
    const logger = new Logger(`${this.name}:${childName}`, this.options);

    // Wrap methods to include default context
    if (defaultContext) {
      const originalDebug = logger.debug.bind(logger);
      const originalInfo = logger.info.bind(logger);
      const originalWarn = logger.warn.bind(logger);
      const originalError = logger.error.bind(logger);

      logger.debug = (message: string, context?: LogContext) => {
        originalDebug(message, { ...defaultContext, ...context });
      };

      logger.info = (message: string, context?: LogContext) => {
        originalInfo(message, { ...defaultContext, ...context });
      };

      logger.warn = (message: string, context?: LogContext) => {
        originalWarn(message, { ...defaultContext, ...context });
      };

      logger.error = (message: string, context?: LogContext, error?: Error) => {
        originalError(message, { ...defaultContext, ...context }, error);
      };
    }

    return logger;
  }
}

/**
 * Create a logger instance
 */
export function createLogger(name: string, options?: Partial<LoggerOptions>): Logger {
  return new Logger(name, options);
}

/**
 * Global logger instance
 */
export const logger = createLogger('DataArchive');

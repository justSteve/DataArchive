/**
 * Retry Policy and Circuit Breaker
 * Provides robust failure handling patterns with exponential backoff and circuit breaking
 */

export interface RetryOptions {
  maxAttempts: number;
  initialDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
  jitter: boolean; // Add randomness to prevent thundering herd
  retryableErrors?: string[]; // Only retry these error messages
}

export interface CircuitBreakerOptions {
  failureThreshold: number; // Number of failures before opening
  successThreshold: number; // Number of successes to close circuit
  timeout: number; // How long to wait before trying again (ms)
  monitoringPeriod: number; // Time window for counting failures (ms)
}

export interface RetryResult<T> {
  success: boolean;
  result?: T;
  error?: Error;
  attempts: number;
  totalDuration: number;
}

export interface CircuitState {
  state: 'closed' | 'open' | 'half-open';
  failures: number;
  successes: number;
  lastFailureTime?: number;
  nextAttemptTime?: number;
}

const DEFAULT_RETRY_OPTIONS: RetryOptions = {
  maxAttempts: 3,
  initialDelayMs: 1000,
  maxDelayMs: 30000,
  backoffMultiplier: 2,
  jitter: true
};

const DEFAULT_CIRCUIT_OPTIONS: CircuitBreakerOptions = {
  failureThreshold: 5,
  successThreshold: 2,
  timeout: 60000,
  monitoringPeriod: 120000
};

/**
 * Retry a function with exponential backoff
 */
export class RetryPolicy {
  private options: RetryOptions;

  constructor(options: Partial<RetryOptions> = {}) {
    this.options = { ...DEFAULT_RETRY_OPTIONS, ...options };
  }

  /**
   * Execute a function with retry logic
   */
  async execute<T>(fn: () => Promise<T>): Promise<RetryResult<T>> {
    const startTime = Date.now();
    let lastError: Error | undefined;
    let attempts = 0;

    for (let i = 0; i < this.options.maxAttempts; i++) {
      attempts++;

      try {
        const result = await fn();
        return {
          success: true,
          result,
          attempts,
          totalDuration: Date.now() - startTime
        };
      } catch (error: any) {
        lastError = error;

        // Check if error is retryable
        if (this.options.retryableErrors) {
          const isRetryable = this.options.retryableErrors.some(
            msg => error.message && error.message.includes(msg)
          );

          if (!isRetryable) {
            console.log(`[RetryPolicy] Error not retryable: ${error.message}`);
            break;
          }
        }

        // Don't delay after last attempt
        if (i < this.options.maxAttempts - 1) {
          const delay = this.calculateDelay(i);
          console.log(`[RetryPolicy] Attempt ${i + 1}/${this.options.maxAttempts} failed, retrying in ${delay}ms...`);
          await this.sleep(delay);
        }
      }
    }

    return {
      success: false,
      error: lastError,
      attempts,
      totalDuration: Date.now() - startTime
    };
  }

  /**
   * Calculate delay with exponential backoff and optional jitter
   */
  private calculateDelay(attemptNumber: number): number {
    const exponentialDelay = Math.min(
      this.options.initialDelayMs * Math.pow(this.options.backoffMultiplier, attemptNumber),
      this.options.maxDelayMs
    );

    if (this.options.jitter) {
      // Add random jitter (±25%)
      const jitter = exponentialDelay * 0.25;
      return exponentialDelay + (Math.random() * jitter * 2 - jitter);
    }

    return exponentialDelay;
  }

  /**
   * Sleep helper
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

/**
 * Circuit Breaker pattern to prevent cascading failures
 */
export class CircuitBreaker {
  private options: CircuitBreakerOptions;
  private state: CircuitState;
  private failureTimestamps: number[];

  constructor(options: Partial<CircuitBreakerOptions> = {}) {
    this.options = { ...DEFAULT_CIRCUIT_OPTIONS, ...options };
    this.state = {
      state: 'closed',
      failures: 0,
      successes: 0
    };
    this.failureTimestamps = [];
  }

  /**
   * Execute a function with circuit breaker protection
   */
  async execute<T>(fn: () => Promise<T>): Promise<T> {
    // Check if circuit is open
    if (this.state.state === 'open') {
      const now = Date.now();
      if (this.state.nextAttemptTime && now < this.state.nextAttemptTime) {
        throw new Error(
          `Circuit breaker is OPEN. Next attempt at ${new Date(this.state.nextAttemptTime).toISOString()}`
        );
      }

      // Transition to half-open
      this.state.state = 'half-open';
      this.state.successes = 0;
      console.log('[CircuitBreaker] Transitioning to HALF-OPEN state');
    }

    try {
      const result = await fn();
      this.recordSuccess();
      return result;
    } catch (error) {
      this.recordFailure();
      throw error;
    }
  }

  /**
   * Record a successful execution
   */
  private recordSuccess(): void {
    if (this.state.state === 'half-open') {
      this.state.successes++;

      if (this.state.successes >= this.options.successThreshold) {
        console.log('[CircuitBreaker] Transitioning to CLOSED state');
        this.state.state = 'closed';
        this.state.failures = 0;
        this.state.successes = 0;
        this.failureTimestamps = [];
      }
    } else if (this.state.state === 'closed') {
      // Reset failure count on success
      this.state.failures = 0;
      this.failureTimestamps = [];
    }
  }

  /**
   * Record a failed execution
   */
  private recordFailure(): void {
    const now = Date.now();
    this.state.lastFailureTime = now;
    this.failureTimestamps.push(now);

    // Remove failures outside monitoring period
    const cutoff = now - this.options.monitoringPeriod;
    this.failureTimestamps = this.failureTimestamps.filter(t => t > cutoff);

    this.state.failures = this.failureTimestamps.length;

    if (this.state.state === 'half-open') {
      // Failure in half-open state immediately opens circuit
      console.warn('[CircuitBreaker] Failure in HALF-OPEN state, transitioning to OPEN');
      this.openCircuit();
    } else if (this.state.state === 'closed') {
      // Check if threshold exceeded
      if (this.state.failures >= this.options.failureThreshold) {
        console.warn(`[CircuitBreaker] Failure threshold (${this.options.failureThreshold}) exceeded, transitioning to OPEN`);
        this.openCircuit();
      }
    }
  }

  /**
   * Open the circuit
   */
  private openCircuit(): void {
    this.state.state = 'open';
    this.state.nextAttemptTime = Date.now() + this.options.timeout;
    this.state.successes = 0;
  }

  /**
   * Get current circuit state
   */
  getState(): CircuitState {
    return { ...this.state };
  }

  /**
   * Manually reset the circuit breaker
   */
  reset(): void {
    console.log('[CircuitBreaker] Manual reset');
    this.state = {
      state: 'closed',
      failures: 0,
      successes: 0
    };
    this.failureTimestamps = [];
  }

  /**
   * Check if circuit is currently allowing requests
   */
  isOpen(): boolean {
    return this.state.state === 'open';
  }
}

/**
 * Combined retry with circuit breaker
 */
export class ResilientExecutor {
  private retryPolicy: RetryPolicy;
  private circuitBreaker: CircuitBreaker;

  constructor(
    retryOptions: Partial<RetryOptions> = {},
    circuitOptions: Partial<CircuitBreakerOptions> = {}
  ) {
    this.retryPolicy = new RetryPolicy(retryOptions);
    this.circuitBreaker = new CircuitBreaker(circuitOptions);
  }

  /**
   * Execute a function with both retry and circuit breaker protection
   */
  async execute<T>(fn: () => Promise<T>): Promise<RetryResult<T>> {
    return this.retryPolicy.execute(async () => {
      return await this.circuitBreaker.execute(fn);
    });
  }

  /**
   * Get circuit breaker state
   */
  getCircuitState(): CircuitState {
    return this.circuitBreaker.getState();
  }

  /**
   * Reset circuit breaker
   */
  resetCircuit(): void {
    this.circuitBreaker.reset();
  }
}

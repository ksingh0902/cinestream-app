import React, { useState, useRef, useCallback } from 'react';
import { RemoteCommandType } from './types';

export const SWIPE_MIN_DISTANCE_PX = 48;
export const TAP_MAX_MOVEMENT_PX = 16;
export const TAP_MAX_DURATION_MS = 450;
export const GESTURE_DEBOUNCE_MS = 90;

export type TouchpadCommand =
  | 'NAVIGATE_UP'
  | 'NAVIGATE_DOWN'
  | 'NAVIGATE_LEFT'
  | 'NAVIGATE_RIGHT'
  | 'SELECT';

interface TvTouchpadProps {
  onCommand: (command: TouchpadCommand) => void;
  disabled?: boolean;
}

interface GesturePoint {
  x: number;
  y: number;
  time: number;
}

const FEEDBACK_LABELS: Record<TouchpadCommand, string> = {
  NAVIGATE_UP: '↑ Up',
  NAVIGATE_DOWN: '↓ Down',
  NAVIGATE_LEFT: '← Left',
  NAVIGATE_RIGHT: '→ Right',
  SELECT: '● Select',
};

function triggerSubtleHaptic(command: TouchpadCommand): void {
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
      navigator.vibrate(command === 'SELECT' ? 18 : 10);
    }
  } catch {
    // Ignore unsupported or blocked haptics (e.g. iOS Safari)
  }
}

export function resolveTouchpadGesture(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
  durationMs: number
): TouchpadCommand | null {
  const deltaX = endX - startX;
  const deltaY = endY - startY;
  const absX = Math.abs(deltaX);
  const absY = Math.abs(deltaY);

  if (Math.max(absX, absY) >= SWIPE_MIN_DISTANCE_PX) {
    if (absX > absY) {
      // Natural horizontal scroll direction: swipe left (deltaX < 0) moves right
      return deltaX > 0 ? 'NAVIGATE_LEFT' : 'NAVIGATE_RIGHT';
    }
    // Natural vertical scroll direction: swipe up (deltaY < 0) moves down to content below
    return deltaY > 0 ? 'NAVIGATE_UP' : 'NAVIGATE_DOWN';
  }

  if (
    absX <= TAP_MAX_MOVEMENT_PX &&
    absY <= TAP_MAX_MOVEMENT_PX &&
    durationMs <= TAP_MAX_DURATION_MS
  ) {
    return 'SELECT';
  }

  return null;
}

export const TvTouchpad: React.FC<TvTouchpadProps> = ({ onCommand, disabled = false }) => {
  const [isPressed, setIsPressed] = useState(false);
  const [feedback, setFeedback] = useState<TouchpadCommand | null>(null);

  const touchStartRef = useRef<GesturePoint | null>(null);
  const touchLatestRef = useRef<{ x: number; y: number } | null>(null);
  const mouseStartRef = useRef<GesturePoint | null>(null);
  const lastTouchTimeRef = useRef<number>(0);
  const lastEmitTimeRef = useRef<number>(0);
  const feedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const emitCommand = useCallback(
    (cmd: TouchpadCommand) => {
      if (disabled) return;
      const now = Date.now();
      if (now - lastEmitTimeRef.current < GESTURE_DEBOUNCE_MS) {
        return;
      }
      lastEmitTimeRef.current = now;
      triggerSubtleHaptic(cmd);
      setFeedback(cmd);
      if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
      feedbackTimerRef.current = setTimeout(() => setFeedback(null), 320);
      onCommand(cmd);
    },
    [disabled, onCommand]
  );

  // Touch handlers (iOS Safari, Android Chrome, touchscreens)
  const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    if (disabled || e.touches.length === 0) return;
    const t = e.touches[0];
    const now = Date.now();
    touchStartRef.current = { x: t.clientX, y: t.clientY, time: now };
    touchLatestRef.current = { x: t.clientX, y: t.clientY };
    setIsPressed(true);
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
    if (!touchStartRef.current || e.touches.length === 0) return;
    const t = e.touches[0];
    touchLatestRef.current = { x: t.clientX, y: t.clientY };
  };

  const handleTouchEnd = (e: React.TouchEvent<HTMLDivElement>) => {
    lastTouchTimeRef.current = Date.now();
    setIsPressed(false);
    const start = touchStartRef.current;
    touchStartRef.current = null;
    if (!start || disabled) {
      touchLatestRef.current = null;
      return;
    }

    const changed = e.changedTouches && e.changedTouches[0];
    const endX = changed ? changed.clientX : touchLatestRef.current?.x ?? start.x;
    const endY = changed ? changed.clientY : touchLatestRef.current?.y ?? start.y;
    touchLatestRef.current = null;

    const cmd = resolveTouchpadGesture(
      start.x,
      start.y,
      endX,
      endY,
      Date.now() - start.time
    );
    if (cmd) {
      emitCommand(cmd);
    }
  };

  const handleTouchCancel = () => {
    touchStartRef.current = null;
    touchLatestRef.current = null;
    setIsPressed(false);
  };

  // Desktop mouse fallback (ignored right after touch events to prevent double-firing)
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disabled || e.button !== 0) return;
    if (Date.now() - lastTouchTimeRef.current < 600) return;
    mouseStartRef.current = { x: e.clientX, y: e.clientY, time: Date.now() };
    setIsPressed(true);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLDivElement>) => {
    setIsPressed(false);
    const start = mouseStartRef.current;
    mouseStartRef.current = null;
    if (!start || disabled) return;
    if (Date.now() - lastTouchTimeRef.current < 600) return;

    const cmd = resolveTouchpadGesture(
      start.x,
      start.y,
      e.clientX,
      e.clientY,
      Date.now() - start.time
    );
    if (cmd) {
      emitCommand(cmd);
    }
  };

  const handleMouseLeave = () => {
    if (mouseStartRef.current) {
      mouseStartRef.current = null;
      setIsPressed(false);
    }
  };

  // Desktop keyboard accessibility fallback
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const keyMap: Record<string, TouchpadCommand> = {
      ArrowUp: 'NAVIGATE_UP',
      ArrowDown: 'NAVIGATE_DOWN',
      ArrowLeft: 'NAVIGATE_LEFT',
      ArrowRight: 'NAVIGATE_RIGHT',
      Enter: 'SELECT',
      ' ': 'SELECT',
    };
    const cmd = keyMap[e.key];
    if (cmd) {
      e.preventDefault();
      emitCommand(cmd);
    }
  };

  return (
    <div className="tv-touchpad-card">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="TV navigation touchpad"
        aria-describedby="tv-touchpad-instructions"
        aria-disabled={disabled}
        data-testid="tv-touchpad"
        className={`tv-touchpad-surface${isPressed ? ' active' : ''}${feedback ? ` feedback-${feedback.toLowerCase()}` : ''}${disabled ? ' disabled' : ''}`}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onTouchCancel={handleTouchCancel}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onKeyDown={handleKeyDown}
      >
        <span className="tv-touchpad-edge tv-touchpad-edge-top" aria-hidden="true" />
        <span className="tv-touchpad-edge tv-touchpad-edge-bottom" aria-hidden="true" />
        <span className="tv-touchpad-edge tv-touchpad-edge-left" aria-hidden="true" />
        <span className="tv-touchpad-edge tv-touchpad-edge-right" aria-hidden="true" />

        <div className="tv-touchpad-center">
          <span className="tv-touchpad-title">TV TOUCHPAD</span>
          <span className="tv-touchpad-subtitle">Swipe to control TV</span>
          <span className="tv-touchpad-hint">
            {feedback ? FEEDBACK_LABELS[feedback] : 'TAP = SELECT'}
          </span>
        </div>
      </div>

      <span id="tv-touchpad-instructions" className="tv-sr-only">
        Swipe up, down, left, or right to navigate the TV. Tap to select.
      </span>
    </div>
  );
};

// Re-export type guard compatibility with RemoteCommandType
export type _TouchpadCommandCheck = TouchpadCommand extends RemoteCommandType ? true : never;

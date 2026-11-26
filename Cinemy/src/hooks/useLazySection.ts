import { useEffect, useRef, useState } from 'react';

interface UseLazySectionOptions {
  /** Preload margin before the section enters the viewport (default: 300px vertical). */
  rootMargin?: string;
  /** Disable observation when the section is not currently mounted/enabled. */
  enabled?: boolean;
}

/**
 * One-shot IntersectionObserver hook for below-the-fold Home sections.
 * - Does not trigger while the section is far below the viewport.
 * - Triggers once as the user scrolls within `rootMargin`.
 * - Never re-triggers on scroll-out / re-entry (prevents duplicate requests).
 * - Falls back to immediate trigger when IntersectionObserver is unavailable.
 */
export function useLazySection(options: UseLazySectionOptions = {}) {
  const { rootMargin = '300px 0px', enabled = true } = options;
  const ref = useRef<HTMLDivElement | null>(null);
  const [isTriggered, setIsTriggered] = useState<boolean>(() => {
    if (!enabled) return false;
    return typeof IntersectionObserver === 'undefined';
  });

  useEffect(() => {
    if (!enabled) return;
    if (isTriggered) return;

    if (typeof IntersectionObserver === 'undefined') {
      setIsTriggered(true);
      return;
    }

    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setIsTriggered(true);
            observer.disconnect();
            break;
          }
        }
      },
      { rootMargin }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [enabled, isTriggered, rootMargin]);

  return { ref, isTriggered };
}

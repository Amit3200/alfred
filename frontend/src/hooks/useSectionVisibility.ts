import { useEffect, useRef, useState } from "react";

const prefix = "alfred-ui-sections:v2:";

function loadStored(key: string): Set<string> | null {
  try {
    const raw = localStorage.getItem(key);
    if (raw) return new Set(JSON.parse(raw) as string[]);
  } catch {
    /* ignore */
  }
  return null;
}

/** Track which addable sections the user has expanded. Configured sections stay collapsed by default. */
export function useSectionVisibility(storageKey: string) {
  const key = prefix + storageKey;

  const [visible, setVisible] = useState<Set<string>>(() => loadStored(key) ?? new Set());

  const saveTimer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      localStorage.setItem(key, JSON.stringify([...visible]));
    }, 120);
    return () => clearTimeout(saveTimer.current);
  }, [key, visible]);

  return {
    isVisible: (id: string) => visible.has(id),
    add: (id: string) => setVisible((s) => new Set(s).add(id)),
    remove: (id: string) =>
      setVisible((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      }),
  };
}

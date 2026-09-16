import { createContext, useContext, useMemo, useState, ReactNode } from "react";
import type { Topic } from "./types";

interface SelectionCtx {
  selected: Record<string, Topic>;
  toggle: (t: Topic) => void;
  isSelected: (id: string) => boolean;
  clear: () => void;
  ids: string[];
}

const Ctx = createContext<SelectionCtx | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<Record<string, Topic>>({});

  const value = useMemo<SelectionCtx>(
    () => ({
      selected,
      toggle: (t: Topic) =>
        setSelected((prev) => {
          const next = { ...prev };
          if (next[t.topicId]) delete next[t.topicId];
          else next[t.topicId] = t;
          return next;
        }),
      isSelected: (id: string) => Boolean(selected[id]),
      clear: () => setSelected({}),
      ids: Object.keys(selected),
    }),
    [selected]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelection(): SelectionCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSelection must be used within SelectionProvider");
  return ctx;
}

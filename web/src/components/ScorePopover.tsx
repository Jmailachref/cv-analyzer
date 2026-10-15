import { useEffect, useRef, useState } from "react";

import { Button, ErrorBanner } from "./ui";

type Props = {
  quote: string;
  anchor: { x: number; y: number };
  onSubmit: (points: number, comment: string) => Promise<void>;
  onClose: () => void;
};

const WIDTH = 320;

export const MAX_POINTS = 20;

// The box a recruiter scores a selected passage in: a number of points and a comment.
export default function ScorePopover({ quote, anchor, onSubmit, onClose }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [points, setPoints] = useState("");
  const value = Number(points);
  const valid = Number.isInteger(value) && value >= 1 && value <= MAX_POINTS;
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [onClose]);

  const submit = async () => {
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit(value, comment.trim());
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  const left = Math.max(8, Math.min(anchor.x - WIDTH / 2, window.innerWidth - WIDTH - 8));
  const top = Math.min(anchor.y + 8, window.innerHeight - 260);

  return (
    <div
      ref={box}
      className="fixed z-50 rounded-lg border border-slate-200 bg-white p-3 shadow-xl"
      style={{ left, top, width: WIDTH }}
    >
      <p className="line-clamp-3 border-l-2 border-blue-500 pl-2 text-xs text-slate-600 italic">{quote}</p>
      <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
        Points
        <input
          autoFocus
          type="number"
          inputMode="numeric"
          min={1}
          max={MAX_POINTS}
          step={1}
          value={points}
          onChange={(e) => setPoints(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="ex. 3"
          className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-base font-semibold tabular-nums"
        />
        <span className="text-xs text-slate-500">de 1 à {MAX_POINTS}</span>
      </label>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
        }}
        placeholder="Commentaire (facultatif)"
        rows={2}
        className="mt-2 w-full resize-none rounded-md border border-slate-300 px-2 py-1.5 text-sm"
      />
      <div className="mt-2">
        <ErrorBanner error={error} />
      </div>
      <div className="mt-2 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Annuler
        </Button>
        <Button variant="primary" onClick={submit} disabled={busy || !valid}>
          {busy ? "…" : valid ? `Donner +${value}` : "Donner"}
        </Button>
      </div>
    </div>
  );
}

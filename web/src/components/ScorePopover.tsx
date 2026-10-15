import { useEffect, useRef, useState } from "react";

import { Button, ErrorBanner } from "./ui";

type Props = {
  quote: string;
  anchor: { x: number; y: number };
  onSubmit: (points: number, comment: string) => Promise<void>;
  onClose: () => void;
};

const WIDTH = 320;

// The box a recruiter scores a selected passage in: +1 to +5 and a comment.
export default function ScorePopover({ quote, anchor, onSubmit, onClose }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [points, setPoints] = useState(3);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (/^[1-5]$/.test(e.key) && document.activeElement?.tagName !== "TEXTAREA") setPoints(Number(e.key));
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
    setBusy(true);
    setError(null);
    try {
      await onSubmit(points, comment.trim());
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
      <div className="mt-3 flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setPoints(n)}
            className={`flex-1 rounded-md py-1.5 text-sm font-semibold transition ${
              points === n ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            +{n}
          </button>
        ))}
      </div>
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
        <Button variant="primary" onClick={submit} disabled={busy}>
          {busy ? "…" : `Donner +${points}`}
        </Button>
      </div>
    </div>
  );
}

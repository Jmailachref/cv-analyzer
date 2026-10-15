import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type Box, type CriterionResult, type DocumentDetail, type Highlight, type Line, type Score } from "../api";
import PdfViewer, { type Selection } from "../components/PdfViewer";
import ScorePopover from "../components/ScorePopover";
import { Button, Card, Empty, ErrorBanner, formatPoints, ScoreBadge, Spinner, StatusBadge } from "../components/ui";
import { go, href } from "../router";

type Pending = { quote: string; anchor: { x: number; y: number }; target: { quote: string; page: number; boxes: Box[] } | { line: number } };

const SECTIONS: Record<string, string> = {
  header: "En-tête",
  summary: "Profil",
  experience: "Expérience",
  education: "Formation",
  skills: "Compétences",
  projects: "Projets",
  languages: "Langues",
  certifications: "Certifications",
  interests: "Centres d'intérêt",
};

export default function DocumentPage({ id, recruiter }: { id: string; recruiter: string }) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [score, setScore] = useState<Score | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [view, setView] = useState<"pdf" | "text" | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [focusLines, setFocusLines] = useState<number[]>([]);

  const load = useCallback(async () => {
    try {
      const [d, s] = await Promise.all([api.document(id), api.score(id)]);
      setDoc(d);
      setScore(s);
    } catch (e) {
      setError(e);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Until the CV is read and scored, check again every two seconds.
  const waiting = doc && (doc.status === "queued" || doc.status === "processing" || (doc.status === "ready" && score?.auto === null));
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [waiting, load]);

  // A scanned CV has no text to select in the PDF: score it from the text OCR read.
  const shown = view ?? (doc?.ocr_used ? "text" : "pdf");

  const lineBoxes = useCallback(
    (numbers: number[]): Box[] =>
      (doc?.lines ?? [])
        .filter((ln) => numbers.includes(ln.n) && ln.bbox)
        .map((ln) => ({ page: ln.page, x0: ln.bbox![0], top: ln.bbox![1], x1: ln.bbox![2], bottom: ln.bbox![3] })),
    [doc],
  );

  const onSelect = (s: Selection) => setPending({ quote: s.quote, anchor: s.anchor, target: { quote: s.quote, page: s.page, boxes: s.boxes } });

  const addHighlight = async (points: number, comment: string) => {
    if (!pending) return;
    await api.addHighlight(id, { author_ref: recruiter, points, comment: comment || null, ...pending.target });
    setPending(null);
    window.getSelection()?.removeAllRanges();
    setScore(await api.score(id));
  };

  const removeHighlight = async (h: Highlight) => {
    await api.deleteHighlight(h.id);
    setScore(await api.score(id));
  };

  const remove = async () => {
    if (!doc || !window.confirm("Supprimer ce CV, sa note et ses surlignages ? C'est définitif.")) return;
    await api.deleteDocument(id);
    go({ page: "offer", ref: doc.offer_ref, tab: "candidates" });
  };

  if (error) return <ErrorBanner error={error} />;
  if (!doc || !score) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const highlights = score.highlights;
  const marks = highlights.map((h) => ({ id: h.id, boxes: h.boxes, points: h.points, active: h.id === active }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <a href={href({ page: "offer", ref: doc.offer_ref, tab: "candidates" })} className="text-sm text-slate-500 hover:text-slate-800">
            ← Candidats de l'offre
          </a>
          <h1 className="mt-1 flex items-center gap-3 text-xl font-semibold">
            {doc.external_ref ?? doc.filename}
            <StatusBadge status={doc.status} />
          </h1>
          <p className="text-xs text-slate-500">
            {doc.filename} · {doc.pages ?? "?"} page(s){doc.ocr_used && " · lu par OCR"}
          </p>
        </div>
        <div className="flex gap-2">
          <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-sm">
            {(["pdf", "text"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded px-3 py-1 ${shown === v ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {v === "pdf" ? "PDF" : "Texte lu"}
              </button>
            ))}
          </div>
          <Button variant="danger" onClick={remove}>
            Supprimer
          </Button>
        </div>
      </div>

      {doc.status === "failed" && <ErrorBanner error={`Le CV n'a pas pu être lu : ${doc.error}`} />}
      {doc.status === "unreadable" && <ErrorBanner error="Ce CV ne contient aucun texte lisible, même avec l'OCR." />}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 rounded-lg bg-slate-200/60 p-3">
          {doc.status === "ready" && (
            <p className="mb-3 text-center text-xs text-slate-600">
              {shown === "pdf"
                ? "Sélectionnez un passage du CV pour lui donner des points."
                : "Cliquez une ligne pour lui donner des points."}
            </p>
          )}
          {shown === "pdf" ? (
            <PdfViewer
              url={api.documentFile(id)}
              marks={marks}
              focus={lineBoxes(focusLines)}
              onSelect={doc.status === "ready" ? onSelect : () => undefined}
              onMarkClick={(hid) => {
                setActive(hid);
                document.getElementById(`hl-${hid}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
              }}
            />
          ) : (
            <TextView doc={doc} highlights={highlights} focusLines={focusLines} onPick={(line, anchor) => setPending({ quote: line.text, anchor, target: { line: line.n } })} />
          )}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
          <ScoreCard score={score} waiting={!!waiting} />
          <CriteriaCard
            criteria={score.analysis?.details.criteria ?? []}
            onHover={(c) => setFocusLines(c ? c.lines : [])}
          />
          <Card title={`Passages notés (${highlights.length})`}>
            {highlights.length === 0 ? (
              <Empty>Aucun passage noté pour l'instant.</Empty>
            ) : (
              <ul className="-my-1 space-y-2">
                {highlights.map((h) => (
                  <li
                    id={`hl-${h.id}`}
                    key={h.id}
                    onMouseEnter={() => setActive(h.id)}
                    onMouseLeave={() => setActive(null)}
                    className={`rounded-md border p-2.5 text-sm transition ${h.id === active ? "border-blue-400 bg-blue-50" : "border-slate-200"}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="line-clamp-3 text-slate-700 italic">« {h.quote} »</p>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-bold tabular-nums ${h.points < 0 ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"}`}>{formatPoints(h.points)}</span>
                    </div>
                    {h.comment && <p className="mt-1.5 text-slate-900">{h.comment}</p>}
                    <div className="mt-1.5 flex items-center justify-between text-xs text-slate-500">
                      <span>
                        {h.author_ref} · {new Date(h.created_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
                      </span>
                      <button onClick={() => removeHighlight(h)} className="text-red-600 hover:underline">
                        Retirer
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </aside>
      </div>

      {pending && <ScorePopover quote={pending.quote} anchor={pending.anchor} onSubmit={addHighlight} onClose={() => setPending(null)} />}
    </div>
  );
}

function ScoreCard({ score, waiting }: { score: Score; waiting: boolean }) {
  const details = score.analysis?.details;
  const flags = score.highlights.filter((h) => h.points < 0).length;
  return (
    <Card title="Points" actions={waiting && <Spinner />}>
      <div className="flex items-center gap-3">
        <ScoreBadge value={score.total} className="px-4 py-2 text-3xl" />
        <div className="text-sm text-slate-600">
          Total du CV
          <div className="text-xs text-slate-500">La somme de tous les points, sans limite. Le classement suit ce total.</div>
        </div>
      </div>

      <div className="mt-4 space-y-3 text-sm">
        <div className="rounded-md bg-slate-50 p-3">
          <div className="flex justify-between font-medium">
            <span>Mots-clés de l'offre</span>
            <span className="tabular-nums">{formatPoints(score.auto)}</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Chaque compétence trouvée compte une fois, même si elle revient plusieurs fois dans le CV.
            {details && (
              <>
                {" "}
                Ici {formatPoints(details.gained ?? 0)} pour les compétences trouvées
                {details.penalties ? `, ${formatPoints(-details.penalties)} pour les essentielles absentes` : ""}.
              </>
            )}
          </p>
        </div>
        <div className="rounded-md bg-slate-50 p-3">
          <div className="flex justify-between font-medium">
            <span>Vos points</span>
            <span className="tabular-nums">{formatPoints(score.manual)}</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {score.highlights.length
              ? `${score.highlights.length} passage${score.highlights.length > 1 ? "s" : ""} noté${score.highlights.length > 1 ? "s" : ""}${flags ? `, dont ${flags} red flag${flags > 1 ? "s" : ""}` : ""}.`
              : "Aucun passage noté."}{" "}
            De −100 à +100 par passage, chaque passage une seule fois.
          </p>
        </div>
        {score.auto !== null && (
          <p className="text-center text-xs text-slate-500 tabular-nums">
            {formatPoints(score.auto)} {score.manual < 0 ? "−" : "+"} {Math.abs(score.manual)} = {formatPoints(score.total)}
          </p>
        )}
      </div>
    </Card>
  );
}

function CriteriaCard({ criteria, onHover }: { criteria: CriterionResult[]; onHover: (c: CriterionResult | null) => void }) {
  if (!criteria.length) return null;
  const found = criteria.filter((c) => c.found);
  const missing = criteria.filter((c) => !c.found);
  const chip = (c: CriterionResult, color: string) => (
    <li
      key={c.id}
      onMouseEnter={() => onHover(c)}
      onMouseLeave={() => onHover(null)}
      title={c.matched_terms.length ? `Trouvé : ${c.matched_terms.join(", ")}` : undefined}
      className={`inline-flex cursor-default items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}
    >
      {c.label}
      {c.points !== 0 && <span className="tabular-nums opacity-75">{c.points > 0 ? `+${c.points}` : c.points}</span>}
    </li>
  );
  return (
    <Card title="Critères de l'offre">
      <div className="space-y-3 text-sm">
        {found.length > 0 && (
          <div>
            <h3 className="mb-1 text-xs font-medium text-slate-500">Trouvés (survolez pour les voir dans le CV)</h3>
            <ul className="flex flex-wrap gap-1.5">{found.map((c) => chip(c, "bg-emerald-100 text-emerald-800"))}</ul>
          </div>
        )}
        {missing.length > 0 && (
          <div>
            <h3 className="mb-1 text-xs font-medium text-slate-500">Absents</h3>
            <ul className="flex flex-wrap gap-1.5">
              {missing.map((c) => chip(c, c.points < 0 ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-600"))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

function TextView({ doc, highlights, focusLines, onPick }: {
  doc: DocumentDetail;
  highlights: Highlight[];
  focusLines: number[];
  onPick: (line: Line, anchor: { x: number; y: number }) => void;
}) {
  const groups = useMemo(() => {
    const out: { section: string; lines: Line[] }[] = [];
    for (const line of doc.lines) {
      if (out.at(-1)?.section !== line.section) out.push({ section: line.section, lines: [] });
      out.at(-1)!.lines.push(line);
    }
    return out;
  }, [doc.lines]);

  if (!doc.lines.length) return <Empty>Pas de texte lu pour ce CV.</Empty>;

  const pointsOf = (line: Line) =>
    highlights.filter((h) => h.start < line.end && h.end > line.start).reduce((sum, h) => sum + h.points, 0);

  return (
    <div className="mx-auto max-w-3xl rounded-md bg-white p-6 shadow-sm">
      {groups.map((g, i) => (
        <section key={i} className="mb-4">
          <h3 className="mb-1 text-xs font-semibold tracking-wide text-slate-400 uppercase">{SECTIONS[g.section] ?? g.section}</h3>
          {g.lines.map((line) => {
            const points = pointsOf(line);
            return (
              <button
                key={line.n}
                type="button"
                onClick={(e) => {
                  const r = e.currentTarget.getBoundingClientRect();
                  onPick(line, { x: r.left + r.width / 2, y: r.bottom });
                }}
                className={`flex w-full items-start justify-between gap-3 rounded px-2 py-0.5 text-left text-sm hover:bg-blue-50 ${
                  points < 0 ? "bg-red-100" : points ? "bg-yellow-100" : ""
                } ${focusLines.includes(line.n) ? "ring-2 ring-blue-500" : ""}`}
              >
                <span>{line.text}</span>
                {points !== 0 && <span className={`shrink-0 text-xs font-bold ${points < 0 ? "text-red-700" : "text-emerald-700"}`}>{formatPoints(points)}</span>}
              </button>
            );
          })}
        </section>
      ))}
    </div>
  );
}

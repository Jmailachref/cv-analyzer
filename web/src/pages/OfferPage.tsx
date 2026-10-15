import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";

import { api, type Offer, type RankingRow } from "../api";
import OfferForm from "../components/OfferForm";
import { Button, Card, Empty, ErrorBanner, ScoreBadge, Spinner, StatusBadge } from "../components/ui";
import { go, href } from "../router";

type Props = { offerRef: string; tab: "candidates" | "grid" };

export default function OfferPage({ offerRef, tab }: Props) {
  const [offer, setOffer] = useState<Offer | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.offer(offerRef).then(setOffer, setError);
  }, [offerRef]);

  if (error) return <ErrorBanner error={error} />;
  if (!offer) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const tabClass = (active: boolean) =>
    `border-b-2 px-1 pb-2 text-sm font-medium ${active ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"}`;

  return (
    <div className="space-y-6">
      <div>
        <a href={href({ page: "offers" })} className="text-sm text-slate-500 hover:text-slate-800">
          ← Offres
        </a>
        <h1 className="mt-1 text-xl font-semibold">{offer.title}</h1>
        <p className="font-mono text-xs text-slate-500">
          {offer.external_ref} · grille v{offer.grid_version} · {offer.criteria.length} critères
        </p>
      </div>
      <nav className="flex gap-6 border-b border-slate-200">
        <a href={href({ page: "offer", ref: offerRef, tab: "candidates" })} className={tabClass(tab === "candidates")}>
          Candidats
        </a>
        <a href={href({ page: "offer", ref: offerRef, tab: "grid" })} className={tabClass(tab === "grid")}>
          Grille de notation
        </a>
      </nav>
      {tab === "candidates" ? <Candidates offer={offer} /> : <GridTab offer={offer} onSaved={setOffer} />}
    </div>
  );
}

function Candidates({ offer }: { offer: Offer }) {
  const [rows, setRows] = useState<RankingRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => api.ranking(offer.external_ref).then(setRows, setError), [offer.external_ref]);
  useEffect(() => {
    load();
  }, [load]);

  // While CVs are being read, refresh until every one has its score.
  const pending = rows?.some((r) => r.status === "queued" || r.status === "processing" || (r.status === "ready" && r.auto === null));
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [pending, load]);

  return (
    <div className="space-y-6">
      <Upload offerRef={offer.external_ref} onUploaded={load} />
      <ErrorBanner error={error} />
      <Card title="Classement" actions={pending && <span className="flex items-center gap-2 text-xs text-slate-500"><Spinner /> Lecture des CV</span>}>
        {rows === null ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : rows.length === 0 ? (
          <Empty>Aucun CV pour cette offre. Déposez-en ci-dessus.</Empty>
        ) : (
          <div className="-m-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-2 font-medium">#</th>
                  <th className="px-4 py-2 font-medium">Candidat</th>
                  <th className="px-4 py-2 font-medium">Statut</th>
                  <th className="px-4 py-2 text-center font-medium">Auto</th>
                  <th className="px-4 py-2 text-center font-medium">Recruteur</th>
                  <th className="px-4 py-2 text-center font-medium">Final</th>
                  <th className="px-4 py-2 font-medium">Essentielles manquantes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr
                    key={r.document_id}
                    onClick={() => go({ page: "document", id: r.document_id })}
                    className="cursor-pointer hover:bg-slate-50"
                  >
                    <td className="px-4 py-2.5 tabular-nums text-slate-500">{r.rank ?? "–"}</td>
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-slate-900">{r.external_ref ?? r.filename}</div>
                      {r.external_ref && <div className="text-xs text-slate-500">{r.filename}</div>}
                    </td>
                    <td className="px-4 py-2.5">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <ScoreBadge value={r.auto} />
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <ScoreBadge value={r.manual} />
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <ScoreBadge value={r.final} className="text-base" />
                    </td>
                    <td className="px-4 py-2.5 text-red-700">{r.missing.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function Upload({ offerRef, onUploaded }: { offerRef: string; onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [candidate, setCandidate] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const send = async (files: File[]) => {
    const pdfs = files.filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    if (!pdfs.length) {
      setError(new Error("Déposez des fichiers PDF."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      for (const file of pdfs) {
        // A candidate reference only makes sense for a single CV.
        await api.upload(offerRef, file, pdfs.length === 1 ? candidate.trim() || undefined : undefined);
      }
      setCandidate("");
      onUploaded();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    send(Array.from(event.dataTransfer.files));
  };

  return (
    <Card title="Ajouter des CV">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => input.current?.click()}
          className={`flex flex-1 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-6 text-sm transition ${
            dragging ? "border-blue-500 bg-blue-50 text-blue-700" : "border-slate-300 text-slate-500 hover:border-slate-400"
          }`}
        >
          {busy ? <Spinner /> : <span className="font-medium text-slate-700">Déposez des CV en PDF ou cliquez</span>}
          <span className="text-xs">10 Mo maximum par CV, scannés acceptés</span>
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            hidden
            onChange={(e) => {
              send(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
        </div>
        <label className="sm:w-64">
          <span className="text-sm font-medium text-slate-700">Réf. candidat (facultatif)</span>
          <input
            value={candidate}
            onChange={(e) => setCandidate(e.target.value)}
            placeholder="Amina Haddad"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <span className="text-xs text-slate-500">Pour un seul CV ; sinon le nom du fichier sert.</span>
        </label>
      </div>
      <div className="mt-3">
        <ErrorBanner error={error} />
      </div>
    </Card>
  );
}

function GridTab({ offer, onSaved }: { offer: Offer; onSaved: (offer: Offer) => void }) {
  const [saved, setSaved] = useState(false);
  const remove = async () => {
    if (!window.confirm(`Supprimer « ${offer.title} » et tous ses CV ? C'est définitif.`)) return;
    await api.deleteOffer(offer.external_ref);
    go({ page: "offers" });
  };
  return (
    <div className="space-y-6">
      <Card title="Offre et grille" actions={saved && <span className="text-xs text-emerald-700">Enregistré, les CV sont renotés</span>}>
        <OfferForm
          key={`${offer.grid_version}-${offer.updated_at}`}
          offer={offer}
          onSaved={(o) => {
            onSaved(o);
            setSaved(true);
          }}
        />
      </Card>
      <div className="flex justify-end">
        <Button variant="danger" onClick={remove}>
          Supprimer l'offre et ses CV
        </Button>
      </div>
    </div>
  );
}

import { useState, type FormEvent } from "react";

import { api, PRIORITIES, type Criterion, type Offer, type Skill } from "../api";
import { gridFrom, sameGrid } from "../grid";
import { Button, ErrorBanner } from "./ui";

type Props = {
  offer?: Offer;
  onSaved: (offer: Offer) => void;
  onCancel?: () => void;
};

const newRef = () => `offre-${Math.random().toString(36).slice(2, 8)}`;

export default function OfferForm({ offer, onSaved, onCancel }: Props) {
  const [ref, setRef] = useState(offer?.external_ref ?? newRef());
  const [title, setTitle] = useState(offer?.title ?? "");
  const [skills, setSkills] = useState<Skill[]>(offer?.skills.length ? offer.skills : [{ name: "", priority: 1 }]);
  const [alerts, setAlerts] = useState<string[]>(offer?.alerts ?? []);
  const [alertDraft, setAlertDraft] = useState("");
  // An edited grid is sent as is; otherwise the engine builds it from the skills.
  const [criteria, setCriteria] = useState<Criterion[] | null>(() =>
    offer && !sameGrid(offer.criteria, gridFrom(offer.skills, offer.alerts)) ? offer.criteria : null,
  );
  const [showGrid, setShowGrid] = useState(criteria !== null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const filledSkills = skills.filter((s) => s.name.trim());
  const generated = gridFrom(filledSkills, alerts);
  const grid = criteria ?? generated;

  const updateSkill = (i: number, patch: Partial<Skill>) =>
    setSkills((list) => list.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  const addAlert = () => {
    const word = alertDraft.trim();
    if (word && !alerts.includes(word)) setAlerts([...alerts, word]);
    setAlertDraft("");
  };

  const editCriterion = (i: number, patch: Partial<Criterion>) =>
    setCriteria(grid.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const saved = await api.saveOffer(ref.trim(), {
        title: title.trim(),
        skills: filledSkills.map((s) => ({ name: s.name.trim(), priority: s.priority })),
        alerts,
        criteria,
        settings: offer?.settings,
      });
      onSaved(saved);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-[1fr_16rem]">
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Titre de l'offre</span>
          <input
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Data scientist"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Référence</span>
          <input
            required
            disabled={!!offer}
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm disabled:bg-slate-50 disabled:text-slate-500"
          />
          <span className="text-xs text-slate-500">L'id de l'offre dans RecruteHub</span>
        </label>
      </div>

      <div>
        <h3 className="text-sm font-medium text-slate-700">Compétences</h3>
        <p className="text-xs text-slate-500">
          Essentielle : +1, et −20 si absente. Importante et CV seulement : +0,5. Secondaire et bonus : +0,1.
        </p>
        <div className="mt-2 space-y-2">
          {skills.map((skill, i) => (
            <div key={i} className="flex gap-2">
              <input
                value={skill.name}
                onChange={(e) => updateSkill(i, { name: e.target.value })}
                placeholder="Python"
                className="flex-1 rounded-md border border-slate-300 px-3 py-1.5"
              />
              <select
                value={skill.priority}
                onChange={(e) => updateSkill(i, { priority: Number(e.target.value) })}
                className="w-44 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              >
                {Object.entries(PRIORITIES).map(([value, label]) => (
                  <option key={value} value={value}>
                    {value}. {label}
                  </option>
                ))}
              </select>
              <Button type="button" variant="ghost" onClick={() => setSkills(skills.filter((_, j) => j !== i))} aria-label="Retirer">
                ✕
              </Button>
            </div>
          ))}
          <Button type="button" onClick={() => setSkills([...skills, { name: "", priority: 2 }])}>
            + Compétence
          </Button>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium text-slate-700">Mots d'alerte</h3>
        <p className="text-xs text-slate-500">−5 quand ils apparaissent, par exemple « stage » pour un poste senior.</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {alerts.map((word) => (
            <span key={word} className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-sm text-amber-900">
              {word}
              <button type="button" onClick={() => setAlerts(alerts.filter((w) => w !== word))} className="text-amber-700 hover:text-amber-950">
                ✕
              </button>
            </span>
          ))}
          <input
            value={alertDraft}
            onChange={(e) => setAlertDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addAlert();
              }
            }}
            onBlur={addAlert}
            placeholder="Ajouter puis Entrée"
            className="w-44 rounded-md border border-slate-300 px-2 py-1 text-sm"
          />
        </div>
      </div>

      <div className="rounded-lg border border-slate-200">
        <button
          type="button"
          onClick={() => setShowGrid(!showGrid)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-700"
        >
          <span>
            Grille détaillée ({grid.length} critères){criteria && <span className="ml-2 text-xs text-amber-700">modifiée à la main</span>}
          </span>
          <span className="text-slate-400">{showGrid ? "▲" : "▼"}</span>
        </button>
        {showGrid && (
          <div className="border-t border-slate-200 p-4">
            {criteria ? (
              <div className="mb-3 flex items-center justify-between gap-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
                Grille modifiée : les compétences ci-dessus ne la changent plus.
                <Button type="button" onClick={() => setCriteria(null)}>
                  Regénérer depuis les compétences
                </Button>
              </div>
            ) : (
              <p className="mb-3 text-xs text-slate-500">
                Générée depuis les compétences. Modifiez une ligne pour l'ajuster à la main : ajoutez des mots (séparés par des virgules) ou changez les points.
              </p>
            )}
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="pb-2 font-medium">Critère</th>
                  <th className="pb-2 font-medium">Mots en plus</th>
                  <th className="w-24 pb-2 font-medium">Présent</th>
                  <th className="w-24 pb-2 font-medium">Absent</th>
                </tr>
              </thead>
              <tbody>
                {grid.map((c, i) => (
                  <tr key={c.id} className="border-t border-slate-100">
                    <td className="py-1.5 pr-2">
                      <span className={c.kind === "alert" ? "text-amber-800" : ""}>{c.label}</span>
                      {c.kind === "alert" && <span className="ml-1 text-xs text-amber-700">alerte</span>}
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        defaultValue={c.terms.join(", ")}
                        onBlur={(e) => {
                          const terms = e.target.value.split(",").map((t) => t.trim()).filter(Boolean);
                          if (terms.join(",") !== c.terms.join(",")) editCriterion(i, { terms });
                        }}
                        className="w-full rounded border border-slate-200 px-2 py-1"
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="number"
                        step="0.1"
                        value={c.points_present}
                        onChange={(e) => editCriterion(i, { points_present: Number(e.target.value) })}
                        className="w-full rounded border border-slate-200 px-2 py-1 tabular-nums"
                      />
                    </td>
                    <td className="py-1.5">
                      <input
                        type="number"
                        step="1"
                        max={0}
                        disabled={c.kind === "alert"}
                        value={c.points_absent}
                        onChange={(e) => editCriterion(i, { points_absent: Number(e.target.value) })}
                        className="w-full rounded border border-slate-200 px-2 py-1 tabular-nums disabled:bg-slate-50"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ErrorBanner error={error} />
      <div className="flex justify-end gap-2">
        {onCancel && (
          <Button type="button" onClick={onCancel}>
            Annuler
          </Button>
        )}
        <Button type="submit" variant="primary" disabled={saving || !title.trim()}>
          {saving ? "Enregistrement…" : offer ? "Enregistrer" : "Créer l'offre"}
        </Button>
      </div>
    </form>
  );
}

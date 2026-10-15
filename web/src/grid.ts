import type { Criterion, Skill } from "./api";

// The same rules as the engine (analysis/scoring.py), to tell a generated grid from an edited one.
export const PRIORITY_POINTS: Record<number, [number, number]> = {
  1: [1, -20],
  2: [0.5, 0],
  3: [0.1, 0],
  4: [0.5, 0],
  5: [0.1, 0],
};

const DASHES: Record<string, string> = { "’": "'", "‘": "'", "–": "-", "—": "-", " ": " " };

export function normalize(text: string): string {
  return Array.from(text.replace(/[’‘–— ]/g, (c) => DASHES[c]).toLowerCase())
    .map((ch) => {
      const stripped = ch.normalize("NFKD").replace(/\p{M}/gu, "");
      return stripped.length === 1 ? stripped : ch;
    })
    .join("");
}

export function gridFrom(skills: Skill[]): Criterion[] {
  const used = new Set<string>();
  const slug = (name: string) => {
    let base = normalize(name).split(/\s+/).filter(Boolean).join("-").slice(0, 50) || "criterion";
    if (!/^[a-z0-9]/.test(base)) base = `c${base}`;
    let out = base;
    for (let i = 2; used.has(out); i++) out = `${base}-${i}`;
    used.add(out);
    return out;
  };
  return [...skills]
    .sort((a, b) => a.priority - b.priority)
    .map((s) => ({
      id: slug(s.name),
      label: s.name,
      terms: [],
      default_synonyms: true,
      points_present: PRIORITY_POINTS[s.priority][0],
      points_absent: PRIORITY_POINTS[s.priority][1],
    }));
}

export function sameGrid(a: Criterion[], b: Criterion[]): boolean {
  const key = (c: Criterion) =>
    JSON.stringify([c.id, c.label, c.terms, c.default_synonyms, c.points_present, c.points_absent]);
  return a.length === b.length && a.every((c, i) => key(c) === key(b[i]));
}

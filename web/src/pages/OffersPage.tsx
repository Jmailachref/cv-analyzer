import { useEffect, useState } from "react";

import { api, type OfferSummary } from "../api";
import OfferForm from "../components/OfferForm";
import { Button, Card, Empty, ErrorBanner, Spinner } from "../components/ui";
import { go, href } from "../router";

export default function OffersPage() {
  const [offers, setOffers] = useState<OfferSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.offers().then(setOffers, setError);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Offres</h1>
          <p className="text-sm text-slate-500">Chaque CV est envoyé pour une offre et noté selon sa grille.</p>
        </div>
        {!creating && (
          <Button variant="primary" onClick={() => setCreating(true)}>
            + Nouvelle offre
          </Button>
        )}
      </div>

      {creating && (
        <Card title="Nouvelle offre">
          <OfferForm
            onCancel={() => setCreating(false)}
            onSaved={(offer) => go({ page: "offer", ref: offer.external_ref, tab: "candidates" })}
          />
        </Card>
      )}

      <ErrorBanner error={error} />
      <Card>
        {offers === null ? (
          <div className="flex justify-center py-6">
            <Spinner />
          </div>
        ) : offers.length === 0 ? (
          <Empty>Aucune offre pour l'instant. Créez-en une pour envoyer des CV.</Empty>
        ) : (
          <ul className="-my-2 divide-y divide-slate-100">
            {offers.map((offer) => (
              <li key={offer.external_ref}>
                <a
                  href={href({ page: "offer", ref: offer.external_ref, tab: "candidates" })}
                  className="flex items-center justify-between gap-4 rounded-md px-2 py-3 hover:bg-slate-50"
                >
                  <div>
                    <div className="font-medium text-slate-900">{offer.title}</div>
                    <div className="font-mono text-xs text-slate-500">{offer.external_ref}</div>
                  </div>
                  <div className="text-right text-sm text-slate-600">
                    {offer.documents} CV
                    <div className="text-xs text-slate-400">{new Date(offer.updated_at).toLocaleDateString("fr-FR")}</div>
                  </div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

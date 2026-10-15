import DocumentPage from "./pages/DocumentPage";
import OfferPage from "./pages/OfferPage";
import OffersPage from "./pages/OffersPage";
import { useRecruiter } from "./recruiter";
import { href, useRoute } from "./router";

export default function App() {
  const route = useRoute();
  const [recruiter, setRecruiter] = useRecruiter();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4">
          <a href={href({ page: "offers" })} className="flex items-center gap-2 font-semibold text-slate-900">
            <span className="grid size-7 place-items-center rounded-md bg-blue-600 text-xs font-bold text-white">CV</span>
            CV Analyzer
          </a>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            Recruteur
            <input
              value={recruiter}
              onChange={(e) => setRecruiter(e.target.value)}
              className="w-36 rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900"
            />
          </label>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        {route.page === "offers" && <OffersPage />}
        {route.page === "offer" && <OfferPage key={route.ref} offerRef={route.ref} tab={route.tab} />}
        {route.page === "document" && <DocumentPage key={route.id} id={route.id} recruiter={recruiter.trim() || "recruteur"} />}
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";

// Hash routes, so the API can serve the app as static files: #/, #/offers/:ref, #/documents/:id.
export type Route =
  | { page: "offers" }
  | { page: "offer"; ref: string; tab: "candidates" | "grid" }
  | { page: "document"; id: string };

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "offers" && parts[1]) {
    return { page: "offer", ref: parts[1], tab: parts[2] === "grid" ? "grid" : "candidates" };
  }
  if (parts[0] === "documents" && parts[1]) return { page: "document", id: parts[1] };
  return { page: "offers" };
}

export function href(route: Route): string {
  switch (route.page) {
    case "offers":
      return "#/";
    case "offer":
      return `#/offers/${encodeURIComponent(route.ref)}${route.tab === "grid" ? "/grid" : ""}`;
    case "document":
      return `#/documents/${route.id}`;
  }
}

export function go(route: Route): void {
  window.location.hash = href(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

import { useEffect, useState } from "react";

// No sign-in here: the recruiter's name only labels the highlights they add.
const KEY = "cva.recruiter";

function read(): string {
  try {
    return localStorage.getItem(KEY) || "recruteur";
  } catch {
    return "recruteur";
  }
}

export function useRecruiter(): [string, (name: string) => void] {
  const [name, setName] = useState(read);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, name);
    } catch {
      // Private window: the name lasts for this visit only.
    }
  }, [name]);
  return [name, setName];
}

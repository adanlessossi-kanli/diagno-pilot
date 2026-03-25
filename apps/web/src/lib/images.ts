/**
 * Centralized image registry for Diagno-Pilot web app.
 * All images are sourced from Unsplash (free licence).
 * URLs are documented here per REQ 16.7.
 */
export const IMAGES = {
  /** Médecin africain en consultation — Unsplash (licence libre) */
  heroHome: {
    src: "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80",
    alt: "Médecin africain en consultation",
  },
  /** Stéthoscope sur bureau médical — Unsplash (licence libre) */
  loginSide: {
    src: "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&q=80",
    alt: "Stéthoscope sur bureau médical",
  },
  /** Consultation médicale — Unsplash (licence libre) */
  diagnoseHeader: {
    src: "https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?w=600&q=80",
    alt: "Consultation médicale",
  },
  /** Dossier médical vide — Unsplash (licence libre) */
  patientsEmpty: {
    src: "https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?w=400&q=80",
    alt: "Dossier médical vide",
  },
} as const;

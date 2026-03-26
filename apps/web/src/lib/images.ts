/**
 * Registre centralisé des images pour l'application Diagno-Pilot.
 * Toutes les images proviennent d'Unsplash (licence libre).
 * Chaque entrée documente la source, la licence et un texte alternatif en français.
 * Conforme aux exigences 5.1, 5.2, 5.4.
 */

interface ImageEntry {
  src: string;      // URL de l'image
  alt: string;      // Texte alternatif en français
  source: string;   // URL de la page source
  licence: string;  // Libellé de la licence
}

export const IMAGES: Record<string, ImageEntry> = {
  /** Femme médecin africaine avec stéthoscope — photo Eben Kassaye */
  hero: {
    src: "https://images.unsplash.com/photo-1643297654416-05795d62e39c?w=800&q=80",
    alt: "Femme médecin africaine tenant un stéthoscope",
    source: "https://unsplash.com/photos/a-woman-holding-a-stethoscope-in-her-right-hand-Z7TAIOQgjWA",
    licence: "Unsplash Licence libre",
  },
  /** Femme en chemise médicale avec masque — photo Mustafa Omar */
  consultation: {
    src: "https://images.unsplash.com/photo-1594806038872-ff60b98e82c1?w=800&q=80",
    alt: "Professionnelle de santé africaine en chemise médicale portant un masque",
    source: "https://unsplash.com/photos/woman-in-white-red-and-black-striped-crew-neck-long-sleeve-shirt-with-face-mask-WQUWCcDO8uI",
    licence: "Unsplash Licence libre",
  },
  /** Homme en veste blanche — photo Random Institute */
  medecin: {
    src: "https://images.unsplash.com/photo-1551357177-fd346f2cdbd0?w=800&q=80",
    alt: "Médecin africain en veste blanche",
    source: "https://unsplash.com/photos/man-wearing-white-jacket-cd-102yV3qI",
    licence: "Unsplash Licence libre",
  },
  /** Médecin avec patiente — photo National Cancer Institute */
  infirmiere: {
    src: "https://images.unsplash.com/photo-1576669801945-7a346954da5a?w=800&q=80",
    alt: "Infirmière africaine en consultation avec une patiente",
    source: "https://unsplash.com/photos/doctor-sitting-on-desk-talking-to-sitting-woman-TFJw-mTWw_U",
    licence: "Unsplash Licence libre",
  },
  /** Homme donnant un médicament à un enfant — photo Michael Ali */
  patient: {
    src: "https://images.unsplash.com/photo-1694286068362-5dcea7ed282a?w=800&q=80",
    alt: "Professionnel de santé africain administrant un traitement à un enfant",
    source: "https://unsplash.com/photos/a-man-is-giving-a-child-something-to-eat-0LZjRuipr20",
    licence: "Unsplash Licence libre",
  },
  /** Médecin avec patiente dépistage — photo National Cancer Institute */
  equipe: {
    src: "https://images.unsplash.com/photo-1579154341140-5aa3a445d43b?w=800&q=80",
    alt: "Équipe médicale africaine lors d'un examen de dépistage",
    source: "https://unsplash.com/photos/female-doctor-standing-near-woman-patient-doing-breast-cancer-screening-SMxzEaidR20",
    licence: "Unsplash Licence libre",
  },
  /** Personne en blouse avec stéthoscope — photo National Cancer Institute */
  diagnoseHeader: {
    src: "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=800&q=80",
    alt: "Médecin africain en blouse avec stéthoscope consultant sur téléphone",
    source: "https://unsplash.com/photos/person-wearing-lavatory-gown-with-green-stethoscope-on-neck-using-phone-while-standing-L8tWZT4CcVQ",
    licence: "Unsplash Licence libre",
  },
  /** Femme médecin africaine en blouse blanche — photo Ato Aikins */
  loginSide: {
    src: "https://images.unsplash.com/photo-1678695972687-033fa0bdbac9?w=800&q=80",
    alt: "Femme médecin africaine en blouse blanche avec stéthoscope",
    source: "https://unsplash.com/photos/a-woman-wearing-a-white-coat-and-a-stethoscope-TPT4pevJEmQ",
    licence: "Unsplash Licence libre",
  },
  /** Femme africaine souriante avec médicament — photo Ben Masora */
  patientsEmpty: {
    src: "https://images.unsplash.com/photo-1646457414745-25b782fe1a9c?w=800&q=80",
    alt: "Femme africaine souriante tenant un flacon de médicament",
    source: "https://unsplash.com/photos/a-smiling-woman-holding-a-bottle-of-medicine-ustIWODTeLo",
    licence: "Unsplash Licence libre",
  },
};

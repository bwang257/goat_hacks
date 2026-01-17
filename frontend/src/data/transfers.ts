// Hardcoded transfer walk times in seconds
export const TRANSFER_TIMES: Record<string, Record<string, number>> = {
  'place-pktrm': {
    'Red-to-Green': 120,
    'Green-to-Red': 120,
  },
  'place-dwnxg': {
    'Red-to-Orange': 90,
    'Orange-to-Red': 90,
  },
  'place-state': {
    'Orange-to-Blue': 150,
    'Blue-to-Orange': 150,
  },
  'place-gover': {
    'Green-to-Blue': 100,
    'Blue-to-Green': 100,
  },
  'place-north': {
    'Orange-to-Green': 110,
    'Green-to-Orange': 110,
  },
  'place-jfk': {
    'Red-Ashmont-to-Red-Braintree': 60,
    'Red-Braintree-to-Red-Ashmont': 60,
  },
};

// MBTA Line Colors (Official Branding)
export const LINE_COLORS: Record<string, string> = {
  Red: '#DA291C',
  Orange: '#ED8B00',
  Blue: '#003DA5',
  Green: '#00843D',
};

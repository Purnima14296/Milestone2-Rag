const PII_PATTERNS = [
  { kind: "email", pattern: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i },
  { kind: "phone", pattern: /\b(?:\+?91[\s-]?)?[6-9]\d{9}\b/ },
  { kind: "PAN", pattern: /\b[A-Z]{5}[0-9]{4}[A-Z]\b/ },
  { kind: "Aadhaar", pattern: /\b\d{4}\s?\d{4}\s?\d{4}\b/ },
];

export function detectPiiHint(text) {
  for (const { kind, pattern } of PII_PATTERNS) {
    if (pattern.test(text)) {
      return kind;
    }
  }
  return null;
}

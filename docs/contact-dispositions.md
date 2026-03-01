# Contact Disposition Log

Tracks all contact stage changes with justification. Every contact moved to Trash, removed, or reclassified gets logged here with the reasoning and data behind the decision.

**Validation tool:** IPQualityScore Email Validation API
**Process:** No-phone contacts pulled from FUB, emails validated for deliverability, fraud score, honeypot/spam trap status, and abuse history.

---

## Dispositions

| Date | FUB ID | Name | Email | Previous Stage | New Stage | Reason |
|------|--------|------|-------|----------------|-----------|--------|
| 2026-03-01 | 25747 | Clay Rawlings | clayrawlings@aol.com | Lead | Trash | IPQS: honeypot/spam trap, fraud score 65, low deliverability, leaked in breaches. Sending to this address damages sender reputation. |
| 2026-03-01 | 25190 | John Gover | mechanic239@engineer.com | Lead | Trash | IPQS: fraud score 86, engineer.com is a free forwarding service, leaked in breaches. Pattern consistent with fraudulent/bot registration. |
| 2026-03-01 | 25140 | Sandy Maschmeier | 47ysmsj47@gmail.com | Lead | Trash | IPQS: fraud score 86, random-character email pattern (not name-based), consistent with automated/fake signup. |

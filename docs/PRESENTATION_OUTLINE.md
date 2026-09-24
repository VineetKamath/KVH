# Presentation outline: Rate Ledger

*Built for the Final Presentation Template. The rule from the organisers: show the thing running in the
first two minutes. Slides 2–4 are the live demo (`DEMO_SCRIPT.md`), not slides.*

| # | Slide | Content | Visual |
|---|---|---|---|
| 1 | **Rate Ledger: hotel prices that explain themselves** | PixelMinds · APS-02. One line: a transparent dynamic-pricing engine; every price has a reason, a bound and an audit trail. | `docs/screenshots/01-home.png` |
| 2 | **Live: the traveller** | search Udaipur → live prices with a trail → Price Pass → same pass in a new tab → हि / ಕ | app on screen |
| 3 | **Live: the control room** | lower the ceiling in Controls → Curve & clamps shows 30 of 90 clamped → open a ▲ night: "the model wanted ₹6,323.35; the hotel's ceiling set it to ₹6,000.00" | app on screen |
| 4 | **Live: the AI, gated** | the drawer's Kannada explanation (every digit checked) · What-if in plain language → validated config → the same engine | app on screen |
| 5 | **How a price is made** | reference rate → 8 bounded factors → guardrails (weekly, daily, floor/ceiling ∩ operating band, round inward) → published → ledger | README diagram |
| 6 | **What the data taught us** | the nightly rate jitter (11% → 1.3% after the reference rate); ceiling 2.47× floor for every room (→ operating band); about 0.08 bookings per city-night (→ credibility pooling) | before/after curve (`08-desk-curve.png`) |
| 7 | **Accuracy, honestly** | national weekly 88.5% vs a future-seeing oracle 90.4%; daily 63.7% (above the oracle, thanks to bookings on the books); city 95.7% within ±1 booking; band coverage 81% | Metrics screenshot |
| 8 | **Proof, not promises** | I1–I6 invariants, organiser validator PASS, audit chain, checksums: live on the Proof page · 80 + 5 tests · bandit / pip-audit / npm audit clean | `16-desk-proof.png` |
| 9 | **What we cut and why** | flights (1 row per fare) · optimiser (no price response in the data) · Postgres (not needed at this size) · live A/B (the simulator instead) | text |
| 10 | **Thank you** | team names · repo · "Prices that explain themselves, inside limits the hotel controls, on the record." | wordmark |

**Speakers:** two voices at most. One drives the app while the other narrates, and they swap at slide 5.
**Fallback:** a recorded run of slides 2–4 on the machine, offline.

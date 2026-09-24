# Demo script: 3 minutes, app on screen by 0:15

## Before the slot
1. `scripts/start.ps1` (or `sh scripts/start.sh`). Wait for "Rate Ledger on http://127.0.0.1:8000".
2. Save a clean state once: `python -m scripts.snapshot`.
3. Open two browser tabs:
   - Tab 1: `http://127.0.0.1:8000/`
   - Tab 2: `http://127.0.0.1:8000/desk`, signed in with `ADMIN_TOKEN` from `.env`.
4. Close everything else. Have the offline recording ready as a fallback.

**Reset between rehearsals:** stop the server, run `python -m scripts.snapshot --restore`, start again.

## The run

| Time | Click | Say |
|---|---|---|
| 0:00 | Tab 1, the home page | "Rate Ledger is a pricing engine for hotels, and this is its front door. Every price is made from signals, kept inside limits the hotel approved, and recorded." Point at the step list: reference rate → demand → forecast → event → hotel limit → published. |
| 0:20 | **Show rooms** (Udaipur, 12–14 Oct) | "Live prices from the engine. The trail is 90 nights for this room. The brass mark is your check-in night, and the weekend premium is the hotel's own rate card." |
| 0:40 | **Price pass** on Casa Manor Inn | "A held quote, like a boarding pass. The price will not move for 15 minutes." Scroll to **Why this price?**: "Every reason comes from the engine's numbers. The last line is the range this hotel allows tonight." |
| 1:00 | **Open in a new tab** | "Same search, same pass number, same price. Quotes are byte-identical." |
| 1:05 | Header **हि**, then **ಕ** | "Hindi and Kannada, with native digits. The value never changes, only the script." Switch back to **EN**. |
| 1:15 | Tab 2, **Curve & clamps** | "This is the hotel's side, the control room. Each night gets a published price inside its allowed range (shaded). The strip on top shows today's state: next night, the move against the reference rate, clamps, approvals, forecast confidence." |
| 1:35 | **Controls** → Guardrails → Ceiling **6000.00**, reason "Fairness ceiling for festival weeks" → **Save new version** | "The revenue manager sets a fairness ceiling. That creates a new version, writes it to the audit log, and reprices immediately." |
| 1:50 | **Curve & clamps** | "30 of 90 prices clamped, all by the ceiling. Each ▲ is a night where the model wanted more." |
| 2:00 | Click a ▲ night | "The decision record: the model wanted ₹6,323.35, the hotel's ceiling set it to ₹6,000.00. Below that is the exact waterfall from the reference rate, factor by factor, to the paisa. It replays exactly from stored inputs." |
| 2:25 | In the drawer: **ಕನ್ನಡ** under *Traveller explanation* | "The AI writes the traveller's explanation, and a gate checks every digit against the decision before it can ship." |
| 2:40 | **Proof** | "All of this is checked live: every price is in bounds, every price reconstructs and replays, unapproved events change nothing, the organisers' own validator passes, and the audit chain is intact." |
| 2:55 | — | "Prices that explain themselves, inside limits the hotel controls, on the record." |

## If asked
- **Accuracy:** open Metrics → *How close to the best possible?* National weekly accuracy is 88.5%.
  A hindsight oracle that sees the future scores 90.4%. Cities get 0.4 bookings a week, where even the
  oracle scores about 0%, so we report measures built for small counts: 95.7% of city-weeks within ±1
  booking.
- **Events:** Event signals → **Approve** a pending signal (e.g. Jaipur Diwali). Signals are inert until approved,
  then the city's rooms reprice.
- **What-if:** What-if → the chip *"cap the event uplift at 5% and lower the ceiling by 10%"* → **Understand** →
  simulate. The parser rejects anything it doesn't know rather than guessing.
- **Stop everything:** Controls → Kill switch, with a reason. Every room reverts to its reference rate, and live
  holds are honoured.

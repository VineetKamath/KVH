/** The Revenue Desk's sections: one source for the rail, the page headers, the context bar and the palette. */
import { BarChart3, CalendarDays, ClipboardCheck, FlaskConical, LineChart, ScrollText, ShieldCheck, SlidersHorizontal, type LucideIcon } from "lucide-react";

export type Section = { n: number; path: string; label: string; group: "Pricing" | "Analysis" | "Record"; icon: LucideIcon };

export const SECTIONS: readonly Section[] = [
  { n: 1, path: "curve", label: "Curve & clamps", group: "Pricing", icon: LineChart },
  { n: 2, path: "approvals", label: "Approvals", group: "Pricing", icon: ClipboardCheck },
  { n: 3, path: "controls", label: "Controls", group: "Pricing", icon: SlidersHorizontal },
  { n: 4, path: "signals", label: "Event signals", group: "Pricing", icon: CalendarDays },
  { n: 5, path: "simulator", label: "What-if", group: "Analysis", icon: FlaskConical },
  { n: 6, path: "metrics", label: "Metrics", group: "Analysis", icon: BarChart3 },
  { n: 7, path: "audit", label: "Audit log", group: "Record", icon: ScrollText },
  { n: 8, path: "proof", label: "Proof", group: "Record", icon: ShieldCheck },
];

export const sectionByNumber = (n: number) => SECTIONS.find((s) => s.n === n) ?? SECTIONS[0];

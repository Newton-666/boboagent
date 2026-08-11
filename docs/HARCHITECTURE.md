# Bobo Harness Constitution (HARCHITECTURE)

> Version v0.2 (draft) · 2026-08-11 · Drafted by Kimi, pending owner ratification
> Status: CONSTITUTION layer — principles and prohibitions only. No inventory, no procedures.
> Reading chain: this constitution → `data/Agent开发手册` (inventory: what exists) → `docs/GUIDANCE.md` (behavioral map: how to act) → `data/skill-standards/` (operational procedures).
> Authority: every new feature, mode, or ticket MUST pass the §4 admission checklist before work begins. Where legacy behavior conflicts with this constitution, the constitution wins and a rectification ticket is filed.
> Language policy: model-facing normative documents are written in English (consistent with GUIDANCE.md); team collaboration artifacts (tickets, five-check reports, reviews) remain in Chinese.

---

## §1 Legislative History (every principle is backed by a battle scar)

This constitution was not designed; it grew out of these incidents:

| Principle | Origin incident |
|-----------|----------------|
| Explicit modes | 2026-08-11: after owner typed `/office`, the boss agent spent 23 tool calls digging through notes — the model did not know office mode existed (root cause of TICKET-O4) |
| Enforcement at the decision chain | O-1 capability matrix lives at a single point: `core/engine.py::_confirm`; new tools pass through it automatically |
| Control group per ticket | All eight AUTO MODE tickets enforced "zero impact on normal mode" as an acceptance rule; entropy did not spread |
| Snapshots catch what slips through | O-1 review established by measurement: upfront path interception succeeds only ~60-70%; O-3 added snapshot backstop |
| Never trust reports | Two fabrication incidents (false "saved to disk", false "43 passed") established: final review = re-run everything yourself |
| Freeze & exemption | Relay frozen for one week after repair; O-3 RELAY_ORDER exemption scoped to exactly one file, zero scope creep |

---

## §2 The Four Principles

### Principle 1 — A mode is explicit state, not implicit behavior

- Every mode (auto / office / future multi / ...) MUST be session-level explicit state with three elements:
  1. **Switch**: user toggles it explicitly (slash command or environment injection), with state events and resume support.
  2. **Context injection**: while the mode is on, the model's context MUST carry an injected notice — the model must know which mode it is in, what identity it holds, and where its responsibility boundaries are (O-4 standard: mode name / identity / duties / boundaries).
  3. **Capability matrix**: the mode determines the permission tier, codified in `core/command_safety.py` + `data/protected_paths.json`. No verbal discipline substitutes for code.
- Prohibition: **switching UI without switching cognition is an incident-level defect** (a lit status bar the model cannot see).
- Prohibition: no implicit cross-mode leakage — office restrictions must not leak into normal mode, nor the reverse.

### Principle 2 — Enforcement lives at the decision chain, never inside tools

- All interception, validation, and audit hooks attach at exactly one point in the engine decision chain (`_confirm`). New tools and features pass the gate automatically.
- Prohibition: no tool may implement private enforcement logic (distributed enforcement = guaranteed gaps).
- Sole exception channel: written final-review exemption, scoped to named files (precedent: O-3 RELAY_ORDER exemption).

### Principle 3 — Every ticket ships with a control group

- Every ticket's acceptance MUST include the unopened / uninjected / role-less control group: zero impact, zero injection, zero overhead in normal mode — the field is not even read.
- Reporting discipline: five-check reports MUST attach raw test output; reported counts = baseline + new, reconcilable to the exact total.
- Prohibition: "I believe there is no impact" is not acceptance evidence.

### Principle 4 — Admit interception is partial; snapshots catch the rest

- Design upfront interception for ~60-70% success; a **second layer** is mandatory: md5 snapshots of the protected list (snapshot after decision, compare at wrap-up, `office.snap` audit).
- Snapshot semantics: catch, don't enforce (alert + audit, no blocking). Enforcement belongs to the O-1 layer.
- All critical state (tickets, manuals, relay files, library) MUST be traceable: committed to git (force-add anything blocked by .gitignore) + `rollback/pre-*` tags before every merge.

---

## §3 Supporting Principles

1. **Evidence culture**: trust no "done" report; final review = re-run targeted tests + full suite + real-library md5 gate, personally.
2. **Freeze periods**: freshly repaired core components (relay, engine gates) get a freeze window; changes during the window require a final-review exemption.
3. **Degradation leaves a trail**: every degradation (e.g. relay → direct tmux dispatch) writes an audit record: `degradation: time, cause, action, recovery`.
4. **Live isolation**: a live relay and pytest never run concurrently (shared-directory contention causes false failures); stop the relay before running the suite.

---

## §4 Admission Checklist (answer all six before filing any ticket)

1. Which mode does this belong to — normal / auto / office / a new mode? If new, does it satisfy Principle 1's three elements?
2. Do its write operations pass the decision chain? Is `authorized_paths` complete?
3. Where is the control-group test? How is "zero impact on normal mode" proven?
4. Does it touch the protected list or a frozen component? Is an exemption required?
5. Are all artifacts (code / manuals / tickets) fully git-traceable?
6. How will acceptance numbers be reconciled (baseline + new = total)?

---

## §5 Rollout Tasks

- [ ] Restore `data/Agent开发手册` proper (only `Agent开发手册_备份_20260801.md` survives) and update it to 2026-08-11 inventory (add enforcement kernel / wrap-up gate / relay / snapshot layers)
- [ ] Add a one-line pointer to this constitution at the top of `docs/GUIDANCE.md`
- [ ] Align Team Charter v1.1 (staffing / dispatch / degradation) with this constitution and merge

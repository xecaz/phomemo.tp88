# App backlog — a free, private Phomemo/TP88 companion app

The goal: an Android (and eventually desktop) app that drives the TP88 and its whole
M08F/label family **without the paywall, account, ads, or spyware** that wreck the vendor app.
Priorities below are distilled from ~50k words of Google Play reviews (analysed locally; the
raw dumps are not committed) and from our own use; each item notes *why*. The protocol/transport groundwork is already done —
see `docs/tp88-protocol.md`, `docs/tp88-bluetooth.md`, `docs/tp88-models.md`, `src/qy_native.py`,
`src/qy_models.json`.

**Positioning:** *"the free, private, no-subscription Phomemo app that keeps your stencils
un-mirrored, prints at the exact size, and remembers your projects."*

---

## P0 — Non-negotiables (these are the whole reason to switch)

- [ ] **Free, no account, no subscription.** Core printing must never be gated. *Why: #1 rage
      driver by far — "useless unless you pay a ridiculous sub for what was free", "can't print
      a plain image without subscribing", subs that don't sync or keep charging.*
- [ ] **Fully offline.** No server dependency for printing/editing. *Why: "won't work without
      internet to a Chinese server"; templates "fail to load" constantly.*
- [ ] **Minimal permissions** — Bluetooth only; no GPS/contacts/mic; no telemetry. *Why: "demands
      location and contacts… essentially spyware"; "why does a printer app need microphone?"*
- [ ] **No ads, no AI upsell** (any AI is opt-in and hideable). *Why: "plagued with ads"; "shoves
      AI art garbage at every step".*
- [ ] **Rock-solid Bluetooth**: fast connect, **auto-reconnect**, clear status, survives sleep.
      *Why: "98% of the time I can't connect", "have to uninstall/reinstall to print". We've
      already solved reliable bonded BLE — make it bulletproof in-app.*
- [ ] **Reliable mirror toggle** that actually works (and is obvious). *Why: a recent vendor
      update mirrors stencils and the toggle **doesn't turn it off** — "wasted tons of expensive
      stencil paper". Tattoo PPDs default mirror ON (stencils go on face-down); we ship a
      correct, predictable toggle. (Driver side: `tp88_print.py --mirror`.)*
- [ ] **Stability** — never crash on launch/connect/load. *Why: "crashes before I can do
      anything" = instant 1-star.*

## P0 — Core printing & editing

- [ ] **Exact numeric sizing** — type real-world dimensions (mm/inch), with a ruler/grid; not
      pinch-only. *Why: top pro complaint — "can only pinch to 1.02 inches at best"; tattoo
      artists & label makers need precision.*
- [ ] **Free crop + aspect unlock** in-app. *Why: "no crop tool", "aspect ratio locked".*
- [ ] **Accurate WYSIWYG preview** — printed size == previewed size; minimal wasted margins.
      *Why: "says 32mm, prints 43mm"; "wastes so much paper" with blank top/bottom.*
- [ ] **Density & print-speed control** (`1F 11 02` density; blackening). *Why: "photos print
      too dark no matter what", "no way to set print speed".*
- [ ] **Image→clean stencil**: threshold/contrast/line-enhance for crisp 1-bit output. *Why:
      "details get ruined", "grainy", losing fine tattoo lines.*

---

## P1 — The Project system (flagship — nothing in the market does this)

A **Customer → Project → Session** model built around *locked real-world scale*, for
multi-session / large-scale tattoo work.

- [ ] **Calibrate-once, lock the scale.** A Project holds the master hi-res design + a locked
      **pixels-per-mm**. First session you size/place the whole layout and confirm the fit on
      the customer — that *defines* px/mm. *Why (our use): laying out a full-body piece, you
      place placeholder lines, then over later sessions you must re-print regions at the **same**
      scale; today cropping a region "in scale" is painful.*
- [ ] **Crop-and-print any region at the locked scale.** Select a region of the master → it
      prints at the exact consistent real-world size, every session, regardless of which part.
- [ ] **Cross-session alignment / registration.** Store anchor/registration marks and support
      **crop-with-overlap** (each print includes a sliver of the adjacent, already-tattooed
      region) so the new stencil lines up with existing work. *This is the hard part of
      multi-session, not the scaling — design for it from day one.*
- [ ] **Customer profiles with body measurements** (height; chest/waist/stomach/thigh/upper-arm
      circumference…). Seeds initial scale & placement (esp. wrap-around designs where
      circumference matters) and re-fits a design per customer.
- [ ] **Project persistence & organization** — save/restore projects, sessions, prints; local
      only. *Why: vendor "save" is broken — "saved templates become photos I can't edit",
      "have to REDO the project".*

## P1 — Reach & workflow

- [ ] **Whole-family support + auto-detect** (`src/qy_models.json`, 146 models / 3 encoder
      families). Detect via USB `MDL:` → BLE name → serial heuristic → user picker. *Why:
      "use the app with any printer I own", "all Phomemo products in one app", "2 apps for 2
      printers". BT names are unreliable, so layer the detection.*
- [ ] **Multi-image layout + batch / N-copies** — place several images, print the same design
      ×N. *Why: "used to add multiple pieces and size them", "print 100 labels", a 152-helpful
      request.*
- [ ] **Add text / fonts / alignment** (incl. center, multiline). *Why: "can't add text to
      images", "no center align", "more fonts".*
- [ ] **Custom paper sizes** & roll widths. *Why: "why isn't 50mm an option", "more paper sizes".*

## P1 — Output quality

- [ ] **Background removal** for imported photos/diagrams. *Why: repeated request, "wish it had
      remove background".*
- [ ] **Dithering / halftone options** for photos vs line-art stencils.

---

## P2 — Nice-to-haves

- [ ] **Desktop / Chromebook printing path** (we already have USB on Linux). *Why: "would be 5
      stars if it ran on my Chromebook/laptop".*
- [ ] **Tattoo-flash library / import** (bring-your-own; optional). *Why: "more flash sheets",
      "download tattoos in-app".*
- [ ] **Landscape / banner mode.**
- [ ] **Photo-booth / event mode** (print from a parked phone). *Why: niche but a delighted 5★
      request.*
- [ ] **Optional, hideable AI** (image gen / vectorize) — never pushed, never paywalled-by-stealth.

---

## Anti-features (do NOT build — straight from the 1–2★ pile)

- ❌ Subscription/paywall on basic printing · ❌ mandatory account/login · ❌ per-image AI credits
- ❌ ads / daily notification spam · ❌ GPS/contacts/mic permissions · ❌ cloud dependency to print
- ❌ silent feature removal in updates · ❌ a mirror toggle that doesn't actually toggle

## What we already have (foundation)

Reliable bonded **BLE** (MTU 512, ~12 KB/s) and **USB** transports; device-resolution 1-bit
rendering; exact dot-accurate sizing (203 dpi); working **mirror**; density control; the full
**model registry** and **native command vocabulary**. The Project system and editing UI are the
main new build; the printing layer is solved.

---
name: Gabay OFW
description: One calm surface an OFW talks to — near-white ground, one flag-colored glow, one input that never leaves.
colors:
  ground: "#fbfbfa"
  surface: "#ffffff"
  rail: "#f0efed"
  rail-row: "#e9e8e5"
  rail-row-active: "#e3e2df"
  user-bubble: "#efeeec"
  faint: "#f1f1ee"
  ink: "#1f1f1f"
  body: "#444746"
  muted: "#6e7370"
  dim: "#8c918d"
  pine: "#1f5e4a"
  pine-dark: "#163f32"
  urgent: "#ce1126"
  urgent-dark: "#a30e1f"
  flag-blue: "#0038a8"
  flag-gold: "#fcd116"
typography:
  display:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.9rem, 4.6vw, 3rem)"
    fontWeight: 400
    lineHeight: 1.16
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(1.35rem, 2.4vw, 1.7rem)"
    fontWeight: 400
    lineHeight: 1.22
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: "normal"
  reply:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.08rem"
    fontWeight: 400
    lineHeight: 1.62
    letterSpacing: "normal"
  body:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  caption:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.88rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Figtree, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "normal"
rounded:
  sm: "13px"
  md: "18px"
  lg: "24px"
  composer: "32px"
  pill: "999px"
components:
  button-quiet:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0.8rem 1.4rem"
  button-primary:
    backgroundColor: "{colors.pine}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "0.8rem 1.4rem"
  button-primary-hover:
    backgroundColor: "{colors.pine-dark}"
    textColor: "#ffffff"
  button-urgent:
    backgroundColor: "{colors.urgent}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "0.8rem 1.4rem"
  button-urgent-hover:
    backgroundColor: "{colors.urgent-dark}"
    textColor: "#ffffff"
  composer:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.composer}"
    padding: "0.4rem 0.5rem 0.4rem 1.1rem"
  chat-bubble-user:
    backgroundColor: "{colors.user-bubble}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "20px"
    padding: "0.85rem 1.2rem"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "1.15rem 1.3rem"
  opener-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0.6rem 1.1rem"
  rail-item:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.body}"
    rounded: "{rounded.pill}"
    padding: "0.62rem 0.85rem"
  rail-item-active:
    backgroundColor: "{colors.rail-row-active}"
    textColor: "{colors.ink}"
  emergency-pill:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.urgent}"
    rounded: "{rounded.pill}"
    padding: "0.6rem 1rem"
  input-field:
    backgroundColor: "{colors.faint}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.7rem 0.95rem"
---

# Design System: Gabay OFW

## Overview

**Creative North Star: "One Surface, One Glow, One Bar"**

Gabay OFW is one calm surface an Overseas Filipino Worker talks to — often on a
watched phone, in the middle of a bad situation, with a narrow window to act.
The design borrows the shape of an assistant she already trusts how to use: a
near-white ground, white lifted on soft shadow, a floating input at the foot of
the screen. Everything that could be a border has been taken away; the only
things that separate one region from another are a shadow and a stretch of
empty space. Underneath that borrowed calm, the warmth is unmistakably hers —
one diffuse glow drawn from the Philippine flag's blue, red and gold pools
behind the greeting, the mark is a plain rotated square in pine green, and the
first word is "Kumusta". The aesthetic is borrowed; the brand is not.

The system is built by radical subtraction. There is one ground color, not a
palette of surfaces. There is one glow, and it fades the moment a conversation
starts so it never competes with what Gabay is saying. There is one input, and
it never leaves the screen — findings, contact cards, and the record of what
Gabay understood all arrive inside the thread rather than on a screen she has to
navigate to. Stillness is the feature. Type is large and light, weight 400 for
even the biggest headings, so nothing on the page raises its voice.

Exactly one thing is allowed to break the calm: flag red. It marks the
EMERGENCY exit, the delete-everything action, and an urgent finding — and
nothing else, ever. Its rarity is what makes it legible under stress. The
explicit anti-reference is a generic assistant blue: the glow is the flag's
`#0038a8`, never a borrowed brand color, and the design never leans on another
product's identity to feel trustworthy.

**Key Characteristics:**
- Single near-white ground (`#fbfbfa`); white (`#ffffff`) only for surfaces that float
- Zero borders in the current implementation — shadow and space do all separation
- Figtree only, 300–500; headings are large, weight 400, tight-tracked
- One flag-colored glow on the home screen, faded out once messaging begins
- Flag red (`#ce1126`) reserved for urgent affordances, never decoration
- One conversation, one composer that never leaves; no modes, no dashboard
- Rotated pine square as both the brand mark and the agent's speaker mark

## Colors

A warm-neutral field — greys with a faint green cast — carrying one green
identity accent and one red alarm accent, plus the three flag hues that exist
only as light.

### Primary
- **Pine** (`#1f5e4a`): Gabay itself. The rotated-square brand mark, the speaker
  mark before every agent reply, the primary/confirm button fill, the active
  conversation dot, the account avatar, the focus ring (at 35% alpha). It is the
  color of the guide, used with restraint.
- **Pine Deep** (`#163f32`): the hover/pressed state of any pine fill. Never a
  surface color on its own.

### Secondary
- **Flag Red** (`#ce1126`): the single alarm color. EMERGENCY affordance, the
  "delete everything" action, an urgent finding's one line, the "I need help
  now" dot. Also the exact hue seeded into the home glow. Never a background for
  ordinary content, never a decorative rule, never a hover accent.
- **Flag Red Deep** (`#a30e1f`): hover/pressed state of a solid red control, and
  the ink color for an urgent inline warning on a light surface.

### Tertiary
- **Flag Blue** (`#0038a8`) and **Flag Gold** (`#fcd116`): these have no surface,
  text, or control role. They exist only as the other two stops of the home-screen
  glow, at low alpha. If you are filling a shape with flag blue or gold, you are
  off-system.

### Neutral
- **Ground** (`#fbfbfa`): the one page background, everywhere, signed-in and
  signed-out. The default. Most of the screen is this color.
- **Surface** (`#ffffff`): reserved for things that float above the ground — the
  composer, cards, chips, dialogs, the sign-in card, the calm emergency pill.
  Not a section wrapper; if a white box has no reason to float, it should not be
  white.
- **Rail** (`#f0efed`): the left rail's ground — one shade off the page, which is
  the entire mechanism that sets it apart. **Rail Row** (`#e9e8e5`) is a row
  hover; **Rail Row Active** (`#e3e2df`) is the open conversation.
- **User Bubble** (`#efeeec`): the fill of the visitor's own chat turns — a warm
  grey, deliberately quieter than a saturated "sent message" blue.
- **Faint** (`#f1f1ee`): the recessed fill inside a surface — form inputs, the
  phone-number rows inside a contact card, an icon-button hover.
- **Ink** (`#1f1f1f`): primary text and headings.
- **Body** (`#444746`): secondary and supporting text, the bulk of paragraph copy.
- **Muted** (`#6e7370`): captions, placeholder text, timestamps, the "+" glyph.
- **Dim** (`#8c918d`): the faintest labels — section eyebrows, conversation-list
  dots, the least-load-bearing metadata.

### Named Rules
**The One Red Line Rule.** Flag red appears on at most one element per screen and
only ever means *act now* — EMERGENCY, delete-everything, or a single urgent
finding line. Everything else, however important, stays ink. The red's scarcity
is the signal; dilute it and the screen loses its one alarm.

**The Borrowed Light Rule.** Flag blue and flag gold are light, never material.
They may only appear inside the `.ph-glow` gradient at low alpha. No fill, no
text, no border, no icon uses them.

**The One Ground Rule.** `#fbfbfa` is the background of every screen. White is a
signal that an element floats. A white section that isn't a card, input,
message, or dialog is a bug.

## Typography

**Display / Body / Everything Font:** Figtree (with `system-ui`, `-apple-system`,
`Segoe UI`, `sans-serif` fallbacks)

**Character:** One humanist sans carries the entire system at weights 300–500.
Hierarchy comes from size and weight, never a second family. Headings are set at
weight **400** — the same weight as body text — and made to feel like headings
only through scale and tight tracking. The effect is quiet and even; nothing on
the page shouts through boldness.

### Hierarchy
- **Display** (400, `clamp(1.9rem, 4.6vw, 3rem)`, 1.16, `-0.015em`): the screen's
  one big line — "Kumusta, {name}?", "Is your work following your contract?",
  an urgent finding's lead. One per screen.
- **Headline** (400, `clamp(1.35rem, 2.4vw, 1.7rem)`, 1.22, `-0.01em`): section
  titles inside a flow (the sign-in card's "Start now", a findings summary line).
- **Title** (500, `1.05rem`, 1.35): a card's own heading — a contact card title,
  a form section title. The first place weight 500 appears.
- **Reply** (400, `1.08rem`, 1.62): the signature text style — Gabay's own
  replies in the thread, set larger and looser than a chat bubble so a long
  answer reads like prose, not a notification.
- **Body** (400, `1rem`, 1.55): paragraph copy, supporting lines, form values.
- **Caption** (400, `~0.88rem`, 1.5): the dense sub-body tier — a card's reason
  line, contact-row labels, the trust line, timestamps, ack/trail status text.
  In practice this floats between `0.78rem` and `0.95rem` depending on density;
  treat `0.88rem` as its center, not a hard step.
- **Label** (500, `0.8rem`): rail headings, the profile eyebrow (uppercase,
  `0.08em` tracking, pine), quiet metadata. Small, but weight 500 so it holds.

### Named Rules
**The Weight-400 Headline Rule.** Display and headline text is weight 400 — the
body weight. If a heading is set in 600/700 to "make it a heading", the calm is
broken. Reach for size and negative tracking instead.

**The Detected-Language Rule.** Copy is rendered in whichever of English,
Filipino, or Cebuano Gabay detected — never chosen by the user. Institution
names (DMW, OWWA, MWO, DOLE-SEnA) stay verbatim in every language so she can
match them against a physical sign.

## Layout

A two-part shell: a fixed-width left **rail** and a fluid main column. The rail
is `264px` on desktop and collapses to a `68px` icon strip below `900px` — it
stays a rail on every viewport, never a top bar or a hamburger drawer. The main
column holds one of two screens (home or profile); everything else is a message
in the thread.

**Home, empty:** the greeting, the composer, and the opener chips cluster in the
vertical center of the main column (`margin: auto` above and below), sitting over
the glow. **Home, in conversation:** the greeting and chips retire, the message
list takes the height and scrolls internally, and the composer settles at the
foot. The composer is the one element present in both states and never
re-renders across the transition.

**Reading width:** the message thread, the composer, and the opener row share a
`max-width` of ~`47rem`, centered. Agent replies cap at `~40rem`, user bubbles at
`~32rem`. Line length stays constrained even as the workspace grows.

**Rhythm:** there is no formal spacing token scale; spacing is set per context
with `rem` values and `clamp()` for page padding. Message-to-message gap is
`1.5rem` (desktop) / `1.15rem` (mobile). Main-column padding is
`clamp(1.1rem, 4vw, 3rem)` horizontal, with `3.25rem` of top padding on mobile to
clear the fixed emergency pill.

**Single breakpoint:** `900px`. Below it the rail collapses to icons, cards go
full-width, the emergency pill shrinks, and touch targets stay large.

## Elevation & Depth

**Flat by default, lifted on purpose.** Surfaces sit flat on the ground. A shadow
appears for one of two reasons: to say *this element floats above the page* (the
composer, a card, a dialog, a chip), or as a response to state (hover raises a
control's shadow one step). The rail is the exception that proves the rule — it
separates from the page with a one-shade ground shift (`#f0efed` vs `#fbfbfa`)
and no shadow at all. The current implementation uses **no borders anywhere**; a
hairline is permitted only in the rare spot where the lightest shadow would still
read as too heavy, and none exist today.

Shadows are two-layer and warm-neutral: a tight `1–3px` contact shadow plus a
broad diffuse one, both in low-alpha near-black. They are ambient, never
dramatic.

### Shadow Vocabulary
- **xs** (`0 1px 2px rgba(31,31,31,.06), 0 3px 10px rgba(31,31,31,.05)`): the
  faintest lift — opener chips, the language select, a claim row, an icon-button
  hover.
- **sm** (`0 1px 3px rgba(31,31,31,.08), 0 6px 18px rgba(31,31,31,.06)`): the
  default floating surface — cards, the calm emergency pill, quiet buttons, the
  rail's in-thread Case block.
- **md** (`0 1px 3px rgba(31,31,31,.08), 0 12px 34px rgba(31,31,31,.08)`): the
  composer, and the hover state of an `sm` surface. The most lift a routine
  element gets.
- **lg** (`0 20px 50px rgba(26,28,27,.16)`): modal dialogs and the toast only.

### Named Rules
**The No-Line Rule.** Don't add a border to create separation. If two regions
blur together, the fix is more space or a ground-shift, then a shadow — a
`1px solid` line is the wrong tool in this system.

**The Glow-Recedes Rule.** The `.ph-glow` layer is decoration that must never
compete with content. It is present and saturated on the empty home screen and
animates to `opacity: 0` (`0.5s ease`) the instant the thread has a message.

## Shapes

Everything is rounded, and rounded generously — the form language is soft to the
point of friendliness. Corner radii climb in a deliberate scale: `13px` for
recessed inputs and small rows, `18px` for mid containers, `24px` for cards and
dialogs, `32px` for the composer, and a full `999px` pill for every button,
chip, rail row, and the emergency and language controls. Chat bubbles use a flat
`20px`. There are no sharp corners and no cut/beveled edges anywhere.

The one hard-edged shape in the entire system is the **rotated pine square** —
a `~0.75rem` square, `3–5px` radius, turned 45°. It is the brand mark in the
rail and on the loading screen, and it reappears at `~0.95rem` as the speaker
mark before every one of Gabay's replies. It is the system's only geometric
motif and it is always pine, never outlined, never filled with anything else.

## Components

Buttons, cards, inputs, and the composer are **pill-soft and paper-light**:
rounded to friendliness, white-on-warm-grey, weightless — cards laid on a table,
not chrome bolted to a frame. Every interactive target is large enough to hit
with a shaking hand, and state changes are shadow and color shifts under 150ms,
never motion that demands attention.

### Buttons
- **Shape:** full pill (`999px`), padding `0.8rem 1.4rem`.
- **Quiet (default `.button`):** white fill, ink text, `sm` shadow. Hover raises
  to `md`. This is most buttons.
- **Primary (`.ink-button`):** pine fill, white text, **no shadow** (it sits in
  the page, it doesn't float). Hover darkens to Pine Deep.
- **Urgent (`.urgent-button`):** flag-red fill, white text, no shadow. Hover
  darkens to Flag Red Deep. Only for confirming a destructive or emergency
  action inside a dialog.
- **Text (`.text-button`):** no fill, no shadow, muted text → ink on hover. For
  "Sign out" and other tertiary actions.
- **Focus:** `3px` pine ring at 35% alpha, `3px` offset, on every focusable
  element.

### Chips
- **Opener chips:** white pill, ink text, `xs` shadow → `sm` on hover. Used once,
  on the empty home screen, to suggest first messages. They carry the app's one
  bilingual flourish ("Hindi ako nababayaran / I'm not being paid").
- No selected/filter chip state exists.

### Cards / Containers
- **Corner:** `24px` (`rounded.lg`).
- **Background:** white surface.
- **Shadow:** `sm`, flat at rest (see Elevation).
- **Border:** none.
- **Padding:** `~1.15rem 1.3rem`.
- Two kinds: the **contact card** (a title, an optional reason line, phone rows
  on `faint`, an optional urgent hold-line in red) and the **in-thread Case
  block** ("What Gabay has understood" — a dim title over correctable claim rows
  and Safety-Flag pills). Both render inside the message list, pinned below the
  last message; neither is ever a separate screen.

### Inputs / Fields
- **Text fields:** `faint` fill, no border, `13px` radius, `~0.7rem 0.95rem`
  padding. Focus shows the standard pine ring, not a border shift.
- **Language select:** styled as a white pill with `xs` shadow, `appearance:
  none`. It is the only "setting" control and it is deliberately minor.

### Navigation (the rail)
- Flat `#f0efed` ground, no shadow, no border. Brand mark + wordmark at the top,
  "New conversation" and the conversation list in the middle, account controls
  pinned to the bottom.
- Rows are full pills: `body` text, transparent at rest, `rail-row` on hover,
  `rail-row-active` + a pine dot when open.
- Below `900px` every label disappears and rows center their icon/mark in the
  `68px` strip; the delete affordance, hover-only on desktop, becomes always
  visible.

### The Composer (signature component)
A white pill, `32px` radius, `md` shadow, that never leaves the screen. A muted
`+` glyph at the head (attach, prototype), a borderless auto-growing textarea in
the middle, and a **circular mic button at the tail that is the submit control** —
there is no separate "Send" button. Enter sends; Shift+Enter inserts a newline.
Placeholder is "Tell Gabay what is happening" in the detected language.

### The Emergency Affordance (signature component)
A calm white pill fixed to the top-right of every signed-in screen (and repeated,
full-width and red, inside the first-run dialog): a small flag-red dot and
"I need help now" in flag red, `sm` shadow. When the Imminent Danger predicate is
live, an "I'm safe now" pill stacks beneath it. It is quiet on purpose — but it
is always present, always reachable, and always renders its cached action card
with zero model calls.

## Do's and Don'ts

### Do:
- **Do** put every new surface on the `#fbfbfa` ground and reserve white for
  things that genuinely float (cards, inputs, messages, dialogs, chips).
- **Do** separate regions with space, then a one-shade ground shift, then a
  two-layer shadow — in that order.
- **Do** set headings at weight 400 and create hierarchy with size and negative
  tracking (`-0.01em` to `-0.015em`).
- **Do** keep the reading column near `47rem` and agent replies near `40rem`,
  even on a wide screen.
- **Do** render findings, contact cards, and the Case as messages inside the
  thread; the composer must stay visible while she reads them.
- **Do** use the rotated pine square as the only geometric motif — brand mark and
  agent speaker mark, always pine.
- **Do** keep the emergency affordance always on screen and on the zero-model
  path, however quiet it looks.

### Don't:
- **Don't** add a `1px` border to separate anything. The system has none.
- **Don't** use flag red for anything that isn't *act now* — no red headings, no
  red dividers, no red hover states, no more than one red element per screen.
- **Don't** fill a shape with flag blue or flag gold; they exist only inside the
  home glow at low alpha.
- **Don't** let the glow sit under an active conversation — it fades to zero once
  the thread has a message.
- **Don't** introduce a second font family or a bold heading weight.
- **Don't** give Gabay's replies a bubble or a card; they are markless text after
  the pine square.
- **Don't** build a settings screen, a mode picker, or a separate findings page —
  one conversation, one composer, one Case.
- **Don't** show a phone number, office name, distance, or citation that the
  server didn't send (ADR-0002).

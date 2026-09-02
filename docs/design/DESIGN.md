# Dawn One Accent

Status: current frontend design

The frontend uses the **Dawn, one accent** direction and the current four-state
desktop composition (landing, dashboard, conversation, and findings). It should
feel like a quiet conversation with someone on the user's side: warm, spacious,
direct, and easy to operate under stress.

## Core rule

Clay means **act now**. Nothing else uses clay.

Urgent controls, the Crisis Help mode, urgent findings, and immediate contact
actions use clay. Contract Check, profile, navigation, ordinary
controls, and informational content use warm ink and neutral dawn surfaces.

## Tokens

| Role | Value |
| --- | --- |
| Dawn highlight | `#FDF1E5` |
| Dawn surface | `#FCF5ED` |
| Dawn base | `#FAF2E8` |
| Raised surface | `#FFFFFF` |
| Warm ink | `#3F2917` |
| Body text | `#5C4229` |
| Muted text | `#6B5138` |
| Sand border | `#D9C4AE` |
| Soft sand | `#F0E3D3` |
| Clay urgency | `#A8431F` |

The current design is intentionally light-only.

## Typography

- **Newsreader**: display headings, finding titles, and prominent hotline
  numbers.
- **Karla**: body copy, buttons, labels, form controls, and navigation.
- Display headings are regular weight with tight tracking and comfortable line
  height. Body text stays large enough to read on a phone under stress.

## Shape and depth

- Desktop service panels use 30px radii; findings use 22px radii with a
  severity-colored left edge.
- Conversation messages and supporting panels use soft 16-26px radii.
- Primary actions and segmented controls are pills.
- Chat messages use soft corners with one tighter speaker-side corner.
- Shadows are warm, broad, and low contrast.
- Borders are sand-colored and secondary to spacing.

## Interaction

- Interactive targets are at least 56px high where space permits.
- Invite the user to talk in their own words; avoid questionnaire framing.
- Contract Check and Crisis Help remain explicit choices.
- Crisis Help remains visibly available throughout signed-in screens.
- Voice and contract-photo controls are prototype affordances until their real
  capabilities are implemented. They must acknowledge a click without claiming
  recording, camera, upload, or saved data.
- Severity uses a word, a dot pattern, and weight. Color is supplementary.

## Responsive behavior

Mobile converts the desktop composition to a single vertical flow with
bottom-weighted conversation actions.

Desktop is an adaptation, not a phone frame:

- The signed-out view uses an editorial explanation beside one focused sign-in
  panel and an attached clay OWWA strip.
- The dashboard presents two wide service panels, followed by optional
  conversation starters.
- The Contract Check / Help Now switcher sits in the signed-in top bar.
- Contract Check uses a bottom-weighted conversation beside a truthful
  "What you have told us" rail. The rail reflects only information entered in
  the current preview.
- Findings use a compact two-column grid beside a person-first action rail.
- Line lengths remain constrained even when the workspace grows.

## Safety constraints

- Do not show fabricated MWO phone numbers, distances, office status, or legal
  citations.
- Do not claim that prototype interactions record, upload, or save anything.
- Do not use clay decoratively.
- Do not infer the user's mode.

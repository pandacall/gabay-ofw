# Dawn One Accent

Status: current frontend design

The frontend uses the **Dawn, one accent** direction. It should feel like a
quiet conversation with someone on the user's side: warm, spacious, direct,
and easy to operate under stress.

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

- Main cards use 20-26px radii.
- Primary actions and segmented controls are pills.
- Chat messages use soft corners with one tighter speaker-side corner.
- Shadows are warm, broad, and low contrast.
- Borders are sand-colored and secondary to spacing.

## Interaction

- Interactive targets are at least 56px high where space permits.
- Show one question or decision at a time.
- Contract Check and Crisis Help remain explicit choices.
- Crisis Help remains visibly available throughout signed-in screens.
- Voice and contract-photo controls are prototype affordances until their real
  capabilities are implemented. They must acknowledge a click without claiming
  recording, camera, upload, or saved data.
- Severity uses a word, a dot pattern, and weight. Color is supplementary.

## Responsive behavior

Mobile follows the supplied 390px compositions closely with a single vertical
flow and bottom-weighted actions.

Desktop is an adaptation, not a phone frame:

- Content sits in a centered workspace with generous dawn gutters.
- The dashboard presents the two modes side by side.
- Conversation content uses a readable central column with supporting guidance
  alongside it when space allows.
- Findings and contact cards can use two columns, while preserving answer-first
  reading order.
- Line lengths remain constrained even when the workspace grows.

## Safety constraints

- Do not show fabricated MWO phone numbers, distances, office status, or legal
  citations.
- Do not claim that prototype interactions record, upload, or save anything.
- Do not use clay decoratively.
- Do not infer the user's mode.

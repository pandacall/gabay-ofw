# Civic Utility

Status: current frontend design

Gabay OFW is a high-trust public-service tool. Its interface should feel as
clear and dependable as a mature government or financial service: calm under
normal use, unmistakable during urgent use, and easy to scan on a phone.

## Visual contract

- **Public Sans** carries every interface role. Hierarchy comes from size,
  weight, spacing, and rules rather than an editorial display face.
- **Operational navy** (`#10233F`) is the brand and primary-action color.
- **Mineral neutrals** (`#F3F5F6`, `#E9EDF0`, and white) organize content
  without cream nostalgia, decorative texture, or tinted paper effects.
- **Response red** (`#B33A24`) is reserved for urgent help, urgent findings,
  and official immediate-contact actions.
- Geometry is compact and controlled: 6px controls, 10px task surfaces, and
  16px only for major composed panels.
- Thin rules establish information structure. Shadows are reserved for focused
  task surfaces, not used to turn every section into a floating card.

## Composition

- The signed-out screen is a service explanation beside one navy sign-in
  surface with an attached urgent-contact strip.
- The dashboard is a task console: a concise greeting, two ruled service rows,
  and compact conversation starters. It is not a promotional card grid.
- Contract Check is a bottom-weighted workbench once a conversation starts.
  The empty entry state is centered. User facts remain visible in a separate
  summary rail.
- Findings form one inspectable report list. Severity, issue, and applicable
  contract rule align in stable columns; they are not repeated cards.
- Crisis Help uses a white decision surface beside a permanent navy support
  panel. The red OWWA action remains available without competing with every
  other control.
- Profile uses a restrained editorial split with one compact form surface.

## Interaction and accessibility

- Controls name the action they perform and have visible hover, pressed, and
  keyboard-focus states.
- A skip link is the first focusable control.
- Body and placeholder text meet WCAG AA contrast on their surfaces.
- Request failures remain inline beside Contract Check, preserve the failed
  draft, and state both the problem and recovery.
- Voice, photo, save, and read controls remain explicit prototype affordances;
  they never claim an action occurred.
- Responsive layouts preserve information order instead of shrinking desktop
  columns. At narrow widths, the task surface comes before supporting context.

## Safety and truth

- Do not fabricate user answers, legal citations, office locations, contact
  numbers, distances, saved-state claims, or implemented media behavior.
- Do not infer urgency from contract concerns. Users choose Contract Check or
  Crisis Help explicitly.
- Only official contact paths already established by the product may be shown.
- Dynamic Contract Check findings remain backend-generated.

## Required visual review

Frontend work is not complete after DOM assertions.

1. Capture signed-out, dashboard, Contract Check entry, mid-conversation,
   failure, findings, every Crisis Help step, profile, disclaimer, and loading
   with deterministic auth and API fixtures.
2. Review the states at 1440x900 and 390x844. Also inspect 1180x720 and 320x568
   before approval.
3. Check hierarchy, text wrapping, density, alignment, contrast, overflow,
   focus, and truthful state representation.
4. Correct visible defects in one bounded pass, then recapture affected states.
5. Keep screenshots outside the repository as review evidence.

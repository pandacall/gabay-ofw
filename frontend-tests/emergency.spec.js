const { test, expect } = require("@playwright/test");
const { openAsSignedInUser, SAMPLE_CONTACTS, openRailIfDrawer } = require("./test-helpers");

const emergencyCard = {
  type: "safe_floor",
  country: "SA",
  title: "Saudi Arabia — Mga totoong opisina na makakatulong / Real offices that can help",
  reason: "HELP_REQUESTED",
  reason_line: "You asked for help now. These offices are real, and real people answer them.",
  contacts: SAMPLE_CONTACTS,
  hold_line: null,
};

function emergencyButtonNdjson({ active = true, created = true } = {}) {
  // ADR-0009: the button opens an Emergency Conversation. The latch is
  // Conversation state, carried on its own `emergency_latch` line; the
  // `case` line no longer has an `emergency` key. `created` (spec
  // 2026-09-06) is false when a second press reopened the live one.
  const lines = [JSON.stringify({ type: "card", card: emergencyCard })];
  if (active) {
    lines.push(
      JSON.stringify({
        type: "emergency_latch",
        active: true,
        session_id: "emergency-session",
        created,
      }),
    );
  }
  lines.push(
    JSON.stringify({
      type: "case",
      case: { claims: {}, safety_flags: {}, language: null, pending_escalation: null },
      session_id: "emergency-session",
    }),
  );
  return lines.join("\n") + "\n";
}

// The button reopens the Emergency Conversation (ADR-0009), so the client
// also replays its transcript via GET /api/conversations/<id>. It then
// fires the proactive opener (spec 2026-09-06) for a freshly created
// Conversation; by default that returns an empty stream (no greeting), so
// tests not about the opener are unaffected.
async function routeEmergencyButton(page, { fulfill, fulfillOpener } = {}) {
  await page.route("**/api/emergency/button", (route) =>
    fulfill
      ? fulfill(route)
      : route.fulfill({ contentType: "application/x-ndjson", body: emergencyButtonNdjson() }),
  );
  await page.route("**/api/conversations/emergency-session", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body: JSON.stringify({ type: "emergency_latch", active: true }) + "\n",
    }),
  );
  await page.route("**/api/emergency/opener", (route) =>
    fulfillOpener
      ? fulfillOpener(route)
      : route.fulfill({ contentType: "application/x-ndjson", body: "" }),
  );
}

test("the EMERGENCY button is reachable from home and from Profile", async ({ page }) => {
  await openAsSignedInUser(page);
  await expect(page.getByRole("button", { name: "I need help now" })).toBeVisible();

  await openRailIfDrawer(page);
  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByRole("button", { name: "I need help now" })).toBeVisible();
});

test("EMERGENCY stays reachable even before the first-run disclaimer is dismissed", async ({
  page,
}) => {
  await routeEmergencyButton(page);
  await openAsSignedInUser(page, { acceptedDisclaimer: false });

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "I need help now" }).click();

  await expect(dialog).not.toBeVisible();
  await expect(page.locator(".contact-card")).toBeVisible();
});

test("pressing EMERGENCY renders the cached action card with zero /api/chat calls", async ({
  page,
}) => {
  const chatCalls = [];
  await page.route("**/api/chat", (route) => {
    chatCalls.push(route.request().postDataJSON());
    route.continue();
  });
  let emergencyAuth;
  await routeEmergencyButton(page, {
    fulfill: (route) => {
      emergencyAuth = route.request().headers()["authorization"];
      return route.fulfill({
        contentType: "application/x-ndjson",
        body: emergencyButtonNdjson({ active: true }),
      });
    },
  });
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "I need help now" }).click();

  const card = page.locator(".contact-card");
  await expect(card).toBeVisible();
  await expect(card.locator(".card-contact.dialable a.card-contact-phone")).toHaveAttribute(
    "href",
    "tel:+966502850944",
  );
  await expect(page.locator("#chat-input")).toBeVisible();
  expect(emergencyAuth).toEqual("Bearer valid-alice");
  expect(chatCalls).toEqual([]);
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();
});

test("EMERGENCY switches to the home screen synchronously, bypassing the animated screen transition", async ({
  page,
}) => {
  let resolveEmergency;
  const emergencyPromise = new Promise((resolve) => {
    resolveEmergency = resolve;
  });
  await routeEmergencyButton(page, {
    fulfill: async (route) => {
      await emergencyPromise;
      return route.fulfill({
        contentType: "application/x-ndjson",
        body: emergencyButtonNdjson({ active: true }),
      });
    },
  });
  await openAsSignedInUser(page);
  await openRailIfDrawer(page);
  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();

  await page.getByRole("button", { name: "I need help now" }).click();

  await expect(page.locator("#chat-input")).toBeVisible();
  await expect(page.locator("#screen-loading")).toBeHidden();

  resolveEmergency();
  await expect(page.locator(".contact-card")).toBeVisible();
});

test("mark safe stays hidden until this Conversation holds the latch", async ({ page }) => {
  await openAsSignedInUser(page);
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeHidden();
});

test("the mark-safe affordance reacts to the emergency_latch line from the chat stream", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "ack", text: "I hear you.", session_id: "s1" }),
          JSON.stringify({ type: "reply", text: "I hear you.", session_id: "s1" }),
          JSON.stringify({ type: "emergency_latch", active: true, session_id: "s1" }),
          JSON.stringify({
            type: "case",
            case: {
              claims: {},
              safety_flags: { PHYSICAL_ASSAULT_ONGOING: { source: "extraction" } },
              language: "en",
              pending_escalation: { flag: "PHYSICAL_ASSAULT_ONGOING", at: "x" },
            },
            session_id: "s1",
          }),
        ].join("\n") + "\n",
    }),
  );

  await page.locator("#chat-input").fill("Sinasaktan niya ako ngayon.");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();
});

test("a pocket-tap alone cannot clear the latch — mark safe requires a confirming tap", async ({
  page,
}) => {
  const markSafeCalls = [];
  await routeEmergencyButton(page);
  await page.route("**/api/mark-safe/nonce", (route) => {
    markSafeCalls.push("nonce");
    route.fulfill({ json: { nonce: "one-time-nonce" } });
  });
  await page.route("**/api/mark-safe", (route) => {
    markSafeCalls.push("mark-safe");
    route.fulfill({ json: { marked_safe: true, case: {} } });
  });
  await openAsSignedInUser(page);
  await page.getByRole("button", { name: "I need help now" }).click();
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();

  await page.getByRole("button", { name: "I'm safe now" }).click();
  const dialog = page.locator("#mark-safe-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Confirm you are safe");

  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  expect(markSafeCalls).toEqual([]);
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();
});

test("confirming mark safe clears the latch through the nonce-gated backend", async ({ page }) => {
  const requests = [];
  await routeEmergencyButton(page);
  await page.route("**/api/mark-safe/nonce", (route) => {
    requests.push({ url: "nonce", auth: route.request().headers()["authorization"] });
    route.fulfill({ json: { nonce: "one-time-nonce" } });
  });
  await page.route("**/api/mark-safe", (route) => {
    requests.push({
      url: "mark-safe",
      auth: route.request().headers()["authorization"],
      body: route.request().postDataJSON(),
    });
    route.fulfill({
      json: {
        marked_safe: true,
        case: { claims: {}, safety_flags: { PASSPORT_WITHHELD: { source: "extraction" } } },
      },
    });
  });
  await openAsSignedInUser(page);
  await page.getByRole("button", { name: "I need help now" }).click();
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();

  await page.getByRole("button", { name: "I'm safe now" }).click();
  await page.locator("#mark-safe-dialog").getByRole("button", { name: "Yes, I am safe" }).click();

  await expect(page.getByRole("status")).toContainText("Marked safe.");
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeHidden();
  expect(requests).toEqual([
    { url: "nonce", auth: "Bearer valid-alice" },
    { url: "mark-safe", auth: "Bearer valid-alice", body: { nonce: "one-time-nonce" } },
  ]);
});

test("a failed EMERGENCY call is reported, never silently swallowed", async ({ page }) => {
  await page.route("**/api/emergency/button", (route) =>
    route.fulfill({ status: 503, json: { detail: "down" } }),
  );
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "I need help now" }).click();

  await expect(page.locator(".chat-message.agent.error")).toContainText(
    "Could not reach the emergency card right now",
  );
});

test("a failed mark-safe confirmation is reported, never silently swallowed", async ({ page }) => {
  await routeEmergencyButton(page);
  await page.route("**/api/mark-safe/nonce", (route) =>
    route.fulfill({ status: 503, json: { detail: "down" } }),
  );
  await openAsSignedInUser(page);
  await page.getByRole("button", { name: "I need help now" }).click();
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();

  await page.getByRole("button", { name: "I'm safe now" }).click();
  await page.locator("#mark-safe-dialog").getByRole("button", { name: "Yes, I am safe" }).click();

  await expect(page.getByRole("status")).toContainText("Could not confirm right now.");
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();
});

// The proactive opener (spec 2026-09-06): after the card is on screen,
// EMERGENCY posts one greeting — but only for a freshly created
// Conversation, and never at the cost of the card.

test("the proactive opener greeting streams in after a first press", async ({ page }) => {
  const openerCalls = [];
  await routeEmergencyButton(page, {
    fulfillOpener: (route) => {
      openerCalls.push(route.request().headers()["authorization"]);
      return route.fulfill({
        contentType: "application/x-ndjson",
        body:
          JSON.stringify({
            type: "reply",
            text: "I'm here with you. Do you want help thinking this through, or did you just need these numbers?",
            session_id: "emergency-session",
          }) + "\n",
      });
    },
  });
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "I need help now" }).click();

  await expect(page.locator(".contact-card")).toBeVisible();
  await expect(page.locator(".chat-message.agent").last()).toContainText(
    "Do you want help thinking this through",
  );
  expect(openerCalls).toEqual(["Bearer valid-alice"]);
});

test("a failed opener leaves the card and shows no error", async ({ page }) => {
  await routeEmergencyButton(page, {
    fulfillOpener: (route) => route.fulfill({ status: 500, json: { detail: "model down" } }),
  });
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "I need help now" }).click();

  await expect(page.locator(".contact-card")).toBeVisible();
  await expect(page.locator(".chat-message.agent.error")).toHaveCount(0);
});

test("a second press reopens and does not fire the opener", async ({ page }) => {
  let presses = 0;
  const openerCalls = [];
  await routeEmergencyButton(page, {
    fulfill: (route) => {
      presses += 1;
      return route.fulfill({
        contentType: "application/x-ndjson",
        body: emergencyButtonNdjson({ created: presses === 1 }),
      });
    },
    fulfillOpener: (route) => {
      openerCalls.push(1);
      return route.fulfill({ contentType: "application/x-ndjson", body: "" });
    },
  });
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "I need help now" }).click();
  await expect(page.locator(".contact-card")).toBeVisible();
  await page.getByRole("button", { name: "I need help now" }).click();
  await expect(page.locator(".contact-card")).toBeVisible();

  // Fired once, for the first (creating) press only.
  expect(openerCalls).toEqual([1]);
});

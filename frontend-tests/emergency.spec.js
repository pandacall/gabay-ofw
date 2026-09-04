const { test, expect } = require("@playwright/test");
const { openAsSignedInUser, SAMPLE_CONTACTS, openRailIfDrawer } = require("./test-helpers");

const emergencyCard = {
  type: "safe_floor",
  country: "SA",
  title: "Saudi Arabia — Mga totoong opisina na makakatulong / Real offices that can help",
  reason: "SERVICE_DOWN",
  reason_line: "Nag-render kami mula sa cache. / We are rendering from cache.",
  contacts: SAMPLE_CONTACTS,
  hold_line: null,
};

function emergencyButtonNdjson({ active = true } = {}) {
  return (
    [
      JSON.stringify({ type: "card", card: emergencyCard }),
      JSON.stringify({
        type: "case",
        case: {
          claims: {},
          safety_flags: {},
          language: null,
          emergency: { active, button_pressed_at: "2026-09-03T00:00:00Z" },
        },
        session_id: "emergency-session",
      }),
    ].join("\n") + "\n"
  );
}

test("the EMERGENCY button is reachable from home and from Profile", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await expect(page.getByRole("button", { name: "I need help now" })).toBeVisible();

  await openRailIfDrawer(page);
  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByRole("button", { name: "I need help now" })).toBeVisible();
});

test("EMERGENCY stays reachable even before the first-run disclaimer is dismissed", async ({
  page,
}) => {
  await page.route("**/api/emergency/button", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body: emergencyButtonNdjson({ active: true }),
    }),
  );
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
  await page.route("**/api/emergency/button", (route) => {
    emergencyAuth = route.request().headers()["authorization"];
    route.fulfill({
      contentType: "application/x-ndjson",
      body: emergencyButtonNdjson({ active: true }),
    });
  });
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "I need help now" }).click();

  const card = page.locator(".contact-card");
  await expect(card).toBeVisible();
  await expect(card.locator(".card-contact.dialable a.card-contact-phone")).toHaveAttribute(
    "href",
    "tel:+966502850944",
  );
  // The findings render in the conversation, and the composer never
  // leaves the screen (issue #71) — even for the cached EMERGENCY card.
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
  await page.route("**/api/emergency/button", async (route) => {
    await emergencyPromise;
    route.fulfill({
      contentType: "application/x-ndjson",
      body: emergencyButtonNdjson({ active: true }),
    });
  });
  await openAsSignedInUser(page);
  await openRailIfDrawer(page);
  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByRole("heading", { name: "Your profile" })).toBeVisible();

  await page.getByRole("button", { name: "I need help now" }).click();

  // The screen is already the home screen — composer visible — even
  // though the network call has not resolved yet, and the animated
  // navigate() loading skeleton is never shown: an emergency exit must
  // not wait on a decorative delay (issue #71).
  await expect(page.locator("#chat-input")).toBeVisible();
  await expect(page.locator("#screen-loading")).toBeHidden();

  resolveEmergency();
  await expect(page.locator(".contact-card")).toBeVisible();
});

test("mark safe stays hidden until the Imminent Danger predicate is active", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeHidden();
});

test("the mark-safe affordance reacts to case.emergency.active from the chat stream too", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "ack", text: "I hear you.", session_id: "s1" }),
          JSON.stringify({
            type: "case",
            case: {
              claims: {},
              safety_flags: { PHYSICAL_ASSAULT_ONGOING: { source: "extraction" } },
              language: "en",
              emergency: { active: true },
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

test("a pocket-tap alone cannot clear the predicate — mark safe requires a confirming tap", async ({
  page,
}) => {
  const markSafeCalls = [];
  await page.route("**/api/emergency/button", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body: emergencyButtonNdjson({ active: true }),
    }),
  );
  await page.route("**/api/mark-safe/nonce", (route) => {
    markSafeCalls.push("nonce");
    route.fulfill({ json: { nonce: "one-time-nonce" } });
  });
  await page.route("**/api/mark-safe", (route) => {
    markSafeCalls.push("mark-safe");
    route.fulfill({ json: { marked_safe: true, case: { emergency: { active: false } } } });
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

test("confirming mark safe clears the predicate through the nonce-gated backend", async ({
  page,
}) => {
  const requests = [];
  await page.route("**/api/emergency/button", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body: emergencyButtonNdjson({ active: true }),
    }),
  );
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
        case: { claims: {}, safety_flags: { PASSPORT_WITHHELD: { source: "extraction" } }, emergency: { active: false } },
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

test("a failed EMERGENCY call is reported, never silently swallowed", async ({
  page,
}) => {
  await page.route("**/api/emergency/button", (route) =>
    route.fulfill({ status: 503, json: { detail: "down" } }),
  );
  await openAsSignedInUser(page);

  await page.getByRole("button", { name: "I need help now" }).click();

  await expect(page.locator(".chat-message.agent.error")).toContainText(
    "Could not reach the emergency card right now",
  );
});

test("a failed mark-safe confirmation is reported, never silently swallowed", async ({
  page,
}) => {
  await page.route("**/api/emergency/button", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body: emergencyButtonNdjson({ active: true }),
    }),
  );
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

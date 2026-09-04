const { test, expect } = require("@playwright/test");
const { openAsSignedInUser, SAMPLE_CONTACTS } = require("./test-helpers");

const safeFloorCard = {
  type: "safe_floor",
  country: "SA",
  title: "Saudi Arabia — Real offices that can help",
  reason: "ACUTE_DISCLOSURE",
  reason_line: "You've told me you're in danger right now.",
  contacts: SAMPLE_CONTACTS,
  hold_line: null,
};

function disclosureTurnNdjson() {
  // ADR-0009: an acute disclosure streams the Safe Floor card WITH the
  // Escalation Prompt, then a normal reply — no transfer, no latch line.
  return (
    [
      JSON.stringify({ type: "ack", text: "I hear you.", session_id: "src-1" }),
      JSON.stringify({ type: "card", card: safeFloorCard, session_id: "src-1" }),
      JSON.stringify({
        type: "escalation_prompt",
        escalation_prompt: {
          reason_category: "ASSAULT",
          source_session_id: "src-1",
          country: "SA",
        },
        session_id: "src-1",
      }),
      JSON.stringify({ type: "reply", text: "I'm here with you.", session_id: "src-1" }),
      JSON.stringify({
        type: "case",
        case: {
          claims: {},
          safety_flags: { PHYSICAL_ASSAULT_ONGOING: { source: "extraction" } },
          language: "en",
          pending_escalation: { flag: "PHYSICAL_ASSAULT_ONGOING", at: "x" },
        },
        session_id: "src-1",
      }),
    ].join("\n") + "\n"
  );
}

async function disclose(page) {
  await page.route("**/api/chat", (route) =>
    route.fulfill({ contentType: "application/x-ndjson", body: disclosureTurnNdjson() }),
  );
  await page.locator("#chat-input").fill("sinasaktan niya ako ngayon");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.locator(".escalation-prompt")).toBeVisible();
}

test("an acute disclosure shows the Safe Floor card and the two-tap offer, no screen switch", async ({
  page,
}) => {
  await openAsSignedInUser(page);
  await disclose(page);

  // The card comes WITH the prompt.
  await expect(page.locator(".contact-card")).toBeVisible();
  await expect(page.locator(".escalation-prompt")).toContainText(
    "Do you want to open emergency help?",
  );
  await expect(
    page.getByRole("button", { name: "Open emergency help" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Not now" })).toBeVisible();
  // Danger did not hijack the thread: still the ordinary composer, and
  // the "I'm safe" control is not shown (this thread holds no latch).
  await expect(page.locator("#chat-input")).toBeVisible();
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeHidden();
});

test("declining removes the prompt card only — no request, latch stays off", async ({
  page,
}) => {
  const escalateCalls = [];
  await page.route("**/api/emergency/escalate", (route) => {
    escalateCalls.push(route.request().postDataJSON());
    route.fulfill({ json: { emergency_session_id: "e-1", case: {} } });
  });
  await openAsSignedInUser(page);
  await disclose(page);

  await page.getByRole("button", { name: "Not now" }).click();

  await expect(page.locator(".escalation-prompt")).toBeHidden();
  // The Safe Floor card stays — the number she needs does not vanish.
  await expect(page.locator(".contact-card")).toBeVisible();
  expect(escalateCalls).toEqual([]);
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeHidden();
});

test("confirming opens the Emergency Conversation and shows the I'm-safe control", async ({
  page,
}) => {
  const escalateCalls = [];
  await page.route("**/api/emergency/escalate", (route) => {
    escalateCalls.push(route.request().postDataJSON());
    route.fulfill({ json: { emergency_session_id: "emergency-1", case: {} } });
  });
  // openConversation(emergency-1) replays its transcript — a leading
  // emergency_latch line tells the client this thread holds the latch.
  await page.route("**/api/conversations/emergency-1", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      body:
        [
          JSON.stringify({ type: "emergency_latch", active: true }),
          JSON.stringify({ type: "reply", text: "You're not alone. Are you safe right now?" }),
        ].join("\n") + "\n",
    }),
  );
  await openAsSignedInUser(page);
  await disclose(page);

  await page.getByRole("button", { name: "Open emergency help" }).click();

  expect(escalateCalls).toEqual([{ source_session_id: "src-1" }]);
  await expect(page.getByRole("button", { name: "I'm safe now" })).toBeVisible();
  await expect(page.locator(".messages")).toContainText(
    "You're not alone. Are you safe right now?",
  );
});

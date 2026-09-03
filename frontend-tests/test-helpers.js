// Shared Playwright bootstrap for the static app shell: stubs Firebase
// (auth + config) and the /api/notes endpoint so every spec file signs in
// as the same fixture user ("alice") without touching a real backend.
async function openApp(
  page,
  { acceptedDisclaimer = true, signedIn = true } = {},
) {
  if (acceptedDisclaimer) {
    await page.addInitScript(() =>
      localStorage.setItem("gabay-disclaimer-accepted:alice", "true"),
    );
  }
  await page.route("**/firebase-app.js", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: "export const initializeApp = config => config;",
    }),
  );
  await page.route("**/firebase-auth.js", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: `
        export class GoogleAuthProvider {}
        export const getAuth = () => ({ currentUser: { getIdToken: async () => "valid-alice" } });
        export const signInWithPopup = async () => {};
        export const signOut = async () => {};
        export const onAuthStateChanged = (_auth, callback) =>
          callback(${signedIn ? '{ uid: "alice", displayName: "Alice", email: "alice@example.com" }' : "null"});
      `,
    }),
  );
  await page.route("**/api/firebase-config", (route) =>
    route.fulfill({ json: { apiKey: "test", projectId: "test" } }),
  );
  await page.route("**/api/notes", (route) =>
    route.fulfill({ json: { notes: [] } }),
  );
  await page.goto("/");
}

const openAsSignedInUser = (page, options) => openApp(page, options);

module.exports = { openApp, openAsSignedInUser };

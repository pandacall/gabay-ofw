// Secondary test seam (PRD): Firestore security rules tested directly against
// the emulator. Cross-user reads/writes must fail on every users/{uid}/... path.
import { readFileSync } from "node:fs";
import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";

let env;

before(async () => {
  env = await initializeTestEnvironment({
    projectId: "gabay-ofw-rules-test",
    firestore: { rules: readFileSync("../firestore.rules", "utf8") },
  });
});

after(async () => {
  await env.cleanup();
});

beforeEach(async () => {
  await env.clearFirestore();
});

const alice = () => env.authenticatedContext("alice").firestore();
const bob = () => env.authenticatedContext("bob").firestore();
const anon = () => env.unauthenticatedContext().firestore();

// Every user-scoped path family from the PRD data model, with a payload
// valid for that path (crisisSessions requires an expireAt timestamp).
const writes = (uid) => [
  [`users/${uid}`, { ok: true }],
  [`users/${uid}/notes/n1`, { ok: true }],
  [`users/${uid}/contractChecks/c1`, { ok: true }],
  [`users/${uid}/contractChecks/c1/messages/m1`, { ok: true }],
  [`users/${uid}/crisisSessions/s1`, { expireAt: new Date(Date.now() + 48 * 3600 * 1000) }],
  [`users/${uid}/crisisSessions/s1/messages/m1`, { ok: true }],
];
const paths = (uid) => writes(uid).map(([p]) => p);

describe("owner access", () => {
  it("allows the owner to write and read every user-scoped path", async () => {
    for (const [p, data] of writes("alice")) {
      await assertSucceeds(alice().doc(p).set(data));
      await assertSucceeds(alice().doc(p).get());
    }
  });
});

describe("crisis session TTL invariant", () => {
  it("denies creating a crisis session without expireAt, even for the owner", async () => {
    await assertFails(alice().doc("users/alice/crisisSessions/s2").set({ country: "SA" }));
  });

  it("denies updating a crisis session to drop expireAt", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("users/alice/crisisSessions/s3").set({ expireAt: new Date() });
    });
    await assertFails(
      alice().doc("users/alice/crisisSessions/s3").set({ country: "SA" })
    );
  });

  it("denies a non-timestamp expireAt", async () => {
    await assertFails(
      alice().doc("users/alice/crisisSessions/s4").set({ expireAt: "never" })
    );
  });
});

describe("cross-user isolation", () => {
  it("denies another user reading any of the owner's paths", async () => {
    for (const p of paths("alice")) {
      await assertFails(bob().doc(p).get());
    }
  });

  it("denies another user writing any of the owner's paths", async () => {
    for (const p of paths("alice")) {
      await assertFails(bob().doc(p).set({ hacked: true }));
    }
  });

  it("denies another user deleting the owner's documents", async () => {
    await env.withSecurityRulesDisabled(async (ctx) => {
      await ctx.firestore().doc("users/alice/crisisSessions/s1").set({ x: 1 });
    });
    await assertFails(bob().doc("users/alice/crisisSessions/s1").delete());
  });

  it("denies listing another user's collections", async () => {
    await assertFails(bob().collection("users/alice/contractChecks").get());
  });
});

describe("unauthenticated access", () => {
  it("denies all reads and writes when signed out", async () => {
    for (const p of paths("alice")) {
      await assertFails(anon().doc(p).get());
      await assertFails(anon().doc(p).set({ anon: true }));
    }
  });
});

describe("outside user tree", () => {
  it("denies access to non-user collections by default", async () => {
    await assertFails(alice().doc("admin/config").get());
    await assertFails(alice().doc("admin/config").set({ x: 1 }));
  });

  it("denies user-scoped paths outside the data model, even for the owner", async () => {
    await assertFails(alice().doc("users/alice/random/x1").set({ x: 1 }));
  });
});

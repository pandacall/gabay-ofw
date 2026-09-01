# Gabay OFW

A Gemini-powered web app for Filipino Overseas Foreign Workers (OFWs) in the
Gulf corridor, with two explicitly chosen modes:

- **Contract Check** — describe your contract and your actual conditions; get a
  structured findings report grounded in the six non-negotiable POEA/DMW rules.
  Guidance, never legal advice.
- **Crisis Help ("I Need Help Now")** — a short, calm triage that routes you to
  real resources (1343 Actionline, OWWA 1348, your country's MWO via the
  official DMW directory). Contact cards are rendered by application code,
  never composed by the AI.

Built for the Hack2skill GenAI Academy APAC **Cloud Run AI Challenge**.

## Status

Walking skeleton (issue #2): Firebase Auth (Google Sign-In), user-isolated
Firestore round-trip, Secret Manager key retrieval, Cloud Run deploy.

Contract Check architecture spike (issue #3): resumable ADK 2.0 Workflow,
strict Claims/Findings schemas, deterministic routing, and a custom
Firestore-backed SessionService proven through canned-model HTTP tests. Real
Gemini and UI wiring land in issue #5.

App shell (issue #4): responsive signed-in dashboard, four-language copy,
static click-throughs for both Modes, Findings Report styles, first-run service
limits, optional profile, and a globally available Crisis Help entry.

Live: https://gabay-ofw-417534361115.asia-southeast1.run.app

## Stack

Python 3.11 · FastAPI · `google-adk >= 2.0` · Firebase Authentication ·
Cloud Firestore · Gemini (AI Studio) · Google Cloud Secret Manager · Cloud Run.

## Local development

```bash
pip install -r requirements-dev.txt
python -m pytest tests            # backend tests (HTTP seam, no cloud needed)
```

Run the server locally (needs Application Default Credentials for Firestore):

```bash
set GOOGLE_CLOUD_PROJECT=<project-id>
set FIREBASE_WEB_CONFIG={"apiKey":"...","authDomain":"...","projectId":"..."}
uvicorn --factory app.main:production_app --port 8000
```

### Firestore security-rules tests

Rules and resumable Contract Check persistence are tested directly against the
Firestore emulator (requires Node 18+ and Java 21+ on PATH):

```bash
cd rules-tests
npm install
npm test
npm run test:contract-check
```

## Configuration

| Name | Where | Purpose |
| --- | --- | --- |
| `gemini-api-key` | Secret Manager secret | Gemini API key; fetched at runtime, never in source or env files |
| `GOOGLE_CLOUD_PROJECT` | env (set by Cloud Run) | project for Firestore/Secret Manager |
| `FIREBASE_WEB_CONFIG` | env (JSON) | public Firebase web-app config served to the sign-in page |

## Firestore security rules

`firestore.rules` enforces `request.auth.uid == uid` on **every** path under
`users/{uid}/...` (profile, contractChecks + messages, crisisSessions +
messages). Everything outside the user tree is denied by default. Deploy with:

```bash
firebase deploy --only firestore:rules --project <project-id>
```

## Deploy to Cloud Run

Pushes to `master` automatically run the backend and browser test suites, then
deploy to the production `gabay-ofw` Cloud Run service. The workflow uses
GitHub OIDC and Google Workload Identity Federation, so no service-account key
is stored in GitHub. It can also be run manually from **Actions → Test and
deploy Cloud Run → Run workflow**.

The deployment preserves the service's existing runtime environment and secret
bindings. Repository variables identify the GCP project, region, service, Workload
Identity provider, and deployer service account.

For an intentional one-off deployment:

```bash
gcloud run deploy gabay-ofw \
  --source . \
  --project <project-id> \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --labels dev-tutorial=cloud-run-ai-challenge \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project-id> \
  --set-env-vars ^@^FIREBASE_WEB_CONFIG={"apiKey":"..."}
```

One-time project setup (most steps are automated by `python cloud_setup.py`,
which registers the web app, initializes Identity Platform, releases the
Firestore rules, and authorizes the Cloud Run domain):

1. Enable APIs: `run`, `firestore`, `secretmanager`, `identitytoolkit`,
   `cloudbuild`, `artifactregistry`, `firebase`, `firebaserules`.
2. Add Firebase to the GCP project; enable the **Google** sign-in provider in
   the Firebase console (Authentication → Sign-in method — the one step that
   cannot be done via API because it provisions an OAuth client).
3. Create the Firestore database (native mode).
4. Create the secret and grant the runtime service account access:

   ```bash
   echo -n "<GEMINI_API_KEY>" | gcloud secrets create gemini-api-key --data-file=-
   gcloud secrets add-iam-policy-binding gemini-api-key \
     --member serviceAccount:<runtime-sa> --role roles/secretmanager.secretAccessor
   ```

5. Deploy Firestore rules (see above).

## Privacy & security design (target architecture; enforced pieces noted)

- Per-user isolation enforced by Firestore security rules, not client filtering
  (enforced now — see `firestore.rules` and its emulator tests).
- Crisis sessions must carry an `expireAt` timestamp (enforced in rules now);
  the Firestore TTL policy (48–72 h auto-delete) and manual session deletion
  land with the Crisis Help slice.
- The Gemini key lives only in Secret Manager (enforced now — the app reads the
  env var only when no cloud project is configured, i.e. local dev).
- Contract Check model output is schema-validated before being persisted or
  returned by the API (implemented in the issue #3 architecture spike).

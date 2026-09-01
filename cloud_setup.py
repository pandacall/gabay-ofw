"""One-time cloud setup for Gabay OFW (dedicated project).

Idempotent: safe to re-run. Uses gcloud for tokens; no secrets stored here.
Usage: python cloud_setup.py
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROJECT = "project-54fedfd9-e73a-414e-802"
ACCOUNT = "johncubi11@gmail.com"


def token() -> str:
    out = subprocess.run(
        ["gcloud", "auth", "print-access-token", ACCOUNT],
        capture_output=True, text=True, shell=True, check=True,
    )
    return out.stdout.strip()


def call(method: str, url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token()}")
    req.add_header("x-goog-user-project", PROJECT)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, data) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()}


def ensure_web_app() -> str:
    base = f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT}/webApps"
    apps = call("GET", base).get("apps", [])
    for app in apps:
        if app.get("displayName") == "Gabay OFW":
            print(f"web app exists: {app['appId']}")
            return app["appId"]
    r = call("POST", base, {"displayName": "Gabay OFW"})
    if "_error" in r:
        sys.exit(f"webApps create failed: {r}")
    for _ in range(30):
        time.sleep(2)
        for app in call("GET", base).get("apps", []):
            if app.get("displayName") == "Gabay OFW":
                print(f"web app created: {app['appId']}")
                return app["appId"]
    sys.exit("web app did not appear")


def web_config(app_id: str) -> dict:
    url = f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT}/webApps/{app_id}/config"
    cfg = call("GET", url)
    if "_error" in cfg:
        sys.exit(f"config fetch failed: {cfg}")
    keep = ["apiKey", "authDomain", "projectId", "storageBucket", "messagingSenderId", "appId"]
    return {k: cfg[k] for k in keep if k in cfg}


def try_enable_google_signin() -> bool:
    base = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}"
    existing = call("GET", f"{base}/defaultSupportedIdpConfigs")
    for cfg in existing.get("defaultSupportedIdpConfigs", []):
        if cfg["name"].endswith("google.com") and cfg.get("enabled"):
            print("google sign-in already enabled")
            return True
    r = call(
        "POST",
        f"{base}/defaultSupportedIdpConfigs?idpId=google.com",
        {"enabled": True},
    )
    if "_error" in r:
        print(f"google sign-in enable failed (console step needed): {r}")
        return False
    print("google sign-in enabled")
    return True


def release_rules(rules_path: str) -> None:
    with open(rules_path, encoding="utf-8") as f:
        src = f.read()
    rs = call(
        "POST",
        f"https://firebaserules.googleapis.com/v1/projects/{PROJECT}/rulesets",
        {"source": {"files": [{"name": "firestore.rules", "content": src}]}},
    )
    if "_error" in rs:
        sys.exit(f"ruleset create failed: {rs}")
    release_name = f"projects/{PROJECT}/releases/cloud.firestore"
    body = {"name": release_name, "rulesetName": rs["name"]}
    r = call("POST", f"https://firebaserules.googleapis.com/v1/projects/{PROJECT}/releases", body)
    if r.get("_error") == 409:  # release exists — update it
        r = call(
            "PATCH",
            f"https://firebaserules.googleapis.com/v1/{release_name}",
            {"release": body},
        )
    if "_error" in r:
        sys.exit(f"rules release failed: {r}")
    print(f"rules released: {rs['name']}")


def ensure_auth_initialized() -> None:
    base = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}"
    cfg = call("GET", f"{base}/config")
    if "_error" not in cfg:
        print("identity platform already initialized")
        return
    r = call(
        "POST",
        f"https://identitytoolkit.googleapis.com/v2/projects/{PROJECT}/identityPlatform:initializeAuth",
        {},
    )
    if "_error" in r:
        sys.exit(f"initializeAuth failed: {r}")
    print("identity platform initialized")


def authorize_domain(domain: str) -> None:
    base = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config"
    cfg = call("GET", base)
    domains = cfg.get("authorizedDomains", [])
    if domain in domains:
        print(f"domain already authorized: {domain}")
        return
    domains.append(domain)
    r = call("PATCH", f"{base}?updateMask=authorizedDomains", {"authorizedDomains": domains})
    if "_error" in r:
        sys.exit(f"authorize domain failed: {r}")
    print(f"domain authorized: {domain}")


def main() -> None:
    app_id = ensure_web_app()
    cfg = web_config(app_id)
    with open("web-config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("web config written to web-config.json")
    ensure_auth_initialized()
    try_enable_google_signin()
    release_rules("firestore.rules")
    if len(sys.argv) > 1:
        authorize_domain(sys.argv[1])


if __name__ == "__main__":
    main()

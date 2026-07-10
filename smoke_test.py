#!/usr/bin/env python3
"""Quick smoke test for ifaas-packing HTML server."""
import json
import sys
import urllib.request

PASS = 0
FAIL = 0
BASE = "http://127.0.0.1:8080"

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  PASS: {name}")
        PASS += 1
    except Exception as e:
        print(f"  FAIL: {name} — {e}")
        FAIL += 1

def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
        return json.loads(r.read())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_with_auth(path, token):
    req = urllib.request.Request(f"{BASE}{path}",
        headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

print("=== ifaas-packing 冒烟测试 ===\n")

# 1. Static files
test("GET / → index.html", lambda: urllib.request.urlopen(f"{BASE}/", timeout=5))
test("GET /css/app.css", lambda: urllib.request.urlopen(f"{BASE}/css/app.css", timeout=5))
test("GET /js/app.js", lambda: urllib.request.urlopen(f"{BASE}/js/app.js", timeout=5))

# 2. Config read
test("GET /api/config/server", lambda: get("/api/config/server"))
test("GET /api/config/credentials", lambda: get("/api/config/credentials"))
test("GET /api/config/favorites", lambda: get("/api/config/favorites"))

# 3. Config write
test("POST /api/config/favorites", lambda: post("/api/config/favorites", {"project_ids": ["123", "456"]}))
test("read back favorites", lambda: get("/api/config/favorites"))
# Cleanup
post("/api/config/favorites", {"project_ids": []})

# 4. Security: reject dangerous config names
def check_bad_name(name):
    def _check():
        req = urllib.request.Request(f"{BASE}/api/config/{name}")
        try:
            urllib.request.urlopen(req, timeout=5)
            raise RuntimeError(f"expected HTTPError for '{name}'")
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise RuntimeError(f"expected 400 for '{name}', got {e.code}")
    return _check

def check_empty_name():
    try:
        urllib.request.urlopen(f"{BASE}/api/config/", timeout=5)
        raise RuntimeError("expected error for empty config name")
    except urllib.error.HTTPError:
        pass  # expected — /api/config/ has no name after prefix

test("reject config name '../etc'", check_bad_name("../etc"))
test("reject config name 'a/b'", check_bad_name("a/b"))
test("reject empty config name", check_empty_name)

# 5. Login via proxy
creds = get("/api/config/credentials")
token = None
try:
    resp = post("/api/proxy/rest-auth/login/",
                {"username": creds["username"], "password": creds["password"]})
    assert resp.get("key"), "no token key in response"
    token = resp["key"]
    test("Login via proxy", lambda: None)
except Exception as e:
    test("Login via proxy", lambda: (_ for _ in ()).throw(e))

# 6. Search projects (requires token)
if token:
    try:
        projects = get_with_auth("/api/proxy/api/v1/project/?page=1&pageSize=5&name=", token)
        items = projects if isinstance(projects, list) else projects.get("results", [])
        print(f"  INFO: Found {len(items)} projects")
        test("Search projects", lambda: None)

        if items:
            pid = items[0].get("id") or items[0].get("pk")
            # 7. Get versions
            versions = get_with_auth(f"/api/proxy/api/v1/version/?project_id={pid}", token)
            v_items = versions if isinstance(versions, list) else versions.get("results", [])
            print(f"  INFO: Found {len(v_items)} versions for project {pid}")
            test("Get versions", lambda: None)

            if v_items:
                vid = v_items[0].get("id") or v_items[0].get("pk")
                # 8. Get modules
                modules = get_with_auth(f"/api/proxy/api/v1/module/?version_id={vid}&git_tag=True", token)
                m_items = modules if isinstance(modules, list) else modules.get("results", [])
                print(f"  INFO: Found {len(m_items)} modules for version {vid}")
                test("Get modules", lambda: None)
    except Exception as e:
        test("API flow", lambda: (_ for _ in ()).throw(e))

print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)

"""Diagnose the 404 issue on GET proxy."""
import json, urllib.request, urllib.error, sys

BASE = "http://127.0.0.1:8080"
creds = json.loads(urllib.request.urlopen(f"{BASE}/api/config/credentials"))

# 1. Login
body = json.dumps({"username": creds["username"], "password": creds["password"]}).encode()
req = urllib.request.Request(f"{BASE}/api/proxy/rest-auth/login/",
    data=body, headers={"Content-Type": "application/json"}, method="POST")
try:
    resp = urllib.request.urlopen(req, timeout=10)
    token = json.loads(resp.read())["key"]
    print(f"1. Login: OK (token={token[:16]}...)")
except Exception as e:
    print(f"1. Login FAIL: {e}")
    sys.exit(1)

# 2. Test proxy GET — first check if the handler even receives it
#    Try with a simple request that should definitely work
print("\n2. Testing GET proxy paths:")

tests = [
    "/api/proxy/api/v1/project/?page=1&pageSize=100&name=",
    "/api/proxy/api/v1/project/?page=1&pageSize=100",
]

for path in tests:
    req = urllib.request.Request(f"{BASE}{path}",
        headers={"Authorization": f"Token {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            if isinstance(data, list):
                print(f"   {path} -> 200 OK, {len(data)} items")
            elif isinstance(data, dict):
                keys = list(data.keys())
                for k in ["results", "data", "list", "items"]:
                    if k in data:
                        print(f"   {path} -> 200 OK, {len(data[k])} items in '{k}'")
                        break
                else:
                    print(f"   {path} -> 200 OK, keys: {keys}")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")[:300] if e.fp else ""
        print(f"   {path} -> HTTP {e.code}: {body_text}")
    except Exception as e:
        print(f"   {path} -> ERROR: {e}")

# 3. Also try a direct backend call (bypass proxy) to verify backend
print("\n3. Direct backend test:")
backend = "http://192.168.12.35:3000"
direct_url = f"{backend}/api/v1/project/?page=1&pageSize=5&name="
try:
    req = urllib.request.Request(direct_url,
        headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        items = data if isinstance(data, list) else data.get("results", [])
        print(f"   Direct backend -> 200 OK, {len(items)} items")
except urllib.error.HTTPError as e:
    body_text = e.read().decode(errors="replace")[:300] if e.fp else ""
    print(f"   Direct backend -> HTTP {e.code}: {body_text}")
except Exception as e:
    print(f"   Direct backend -> ERROR: {e}")

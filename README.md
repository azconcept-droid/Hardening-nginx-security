# Hardening-nginx-security

The owasp/modsecurity-crs image ships nginx + ModSecurity + CRS all built in, so you just point it at your backend app.

## How the image works

The container itself acts as a reverse proxy (nginx + ModSecurity inside it) sitting in front of whatever backend you give it via an env var. So the topology is:

Internet/LAN → [modsecurity-crs container:8080] → your backend app (nginx, app server, etc.)

## Custom CRS
Final state of custom-rules/modsecurity-override.conf, loaded before CRS init rule 901160 so it overrides the default.:
1. Rule 900100 — Adds PUT/PATCH/DELETE to tx.allowed_methods (fixes false-positive blocking on all write operations)
2. Rule 900201 — @detectSQLi on REQUEST_URI (catches SQLi in URL path, which CRS ignores by default)
3. Rule 900202 — Chain rule: denies requests with a body on DELETE/GET/HEAD methods

The path traversal on path params (/items/../../etc/passwd) is not blocked by CRS because nginx normalizes the URI to /etc/passwd before ModSecurity sees it — but the attack is already neutralized by nginx (backend returns 404).

## Test the full CRUD flow through the WAF

```
# Create
curl -X POST http://localhost:8080/items \
  -H "Content-Type: application/json" \
  -d '{"name": "widget", "description": "a small widget", "price": 9.99}'
```

```
# List
curl http://localhost:8080/items
```

```
# Get one
curl http://localhost:8080/items/1
```

```
# Update (full)
curl -X PUT http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "widget-v2", "description": "updated", "price": 12.99}'
```

```
# Update (partial)
curl -X PATCH http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"price": 14.99}'
```

```
# Delete
curl -X DELETE http://localhost:8080/items/1
```

## Trigger real detections
**SQLi-looking query param:**
```
curl "http://localhost:8080/search?q=' OR 1=1--"
```

**XSS in JSON body:**
```
curl -X POST http://localhost:8080/items \
  -H "Content-Type: application/json" \
  -d '{"name": "<script>alert(1)</script>", "description": "test"}'
```

**Path traversal:**
```
curl "http://localhost:8080/search?q=../../etc/passwd"
```

### New attack-surface tests worth trying now
**SQLi via PATCH body (numeric field with string injection):**
```
curl -X PATCH http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"price": "1; DROP TABLE items;--"}'
```
This should get blocked at the WAF layer before it even reaches FastAPI's validation — good example of defense-in-depth (FastAPI/Pydantic would reject the type anyway, but CRS should catch the pattern earlier).

**Path traversal / type confusion on path param:**
```
curl http://localhost:8080/items/../../etc/passwd
curl "http://localhost:8080/items/1%27%20OR%20%271%27=%271"
```

**Large/malformed DELETE** with unexpected body (some WAFs flag bodies on DELETE as anomalous):
```
curl -X DELETE http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"reason": "cleanup"}'
```

**Mass assignment attempt via PATCH** (not a WAF concern per se, but good to know CRS won't catch this — it's an app-logic issue, not a signature-based one):
```
curl -X PATCH http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"id": 999, "price": 0.01}'
```
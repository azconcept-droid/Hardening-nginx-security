# Hardening nginx with ModSecurity CRS

A Docker Compose setup that places an OWASP CRS v3.3.10 WAF (nginx + ModSecurity) in front of a FastAPI backend.

## Architecture

```
Client → [modsec-waf :8080] → [api-backend :8000]
            nginx                FastAPI/Uvicorn
            ModSecurity
            OWASP CRS 3.3.10
```

The `owasp/modsecurity-crs:nginx` image bundles nginx, ModSecurity v3, and OWASP CRS into a single reverse-proxy container. Your backend sits behind it on an internal Docker network.

## Project structure

```
.
├── compose.yml
├── custom-rules/
│   └── modsecurity-override.conf   # custom CRS rules (mounted into the WAF)
├── api-backend/
│   ├── Dockerfile
│   ├── main.py                     # FastAPI CRUD app
│   └── requirements.txt
└── README.md
```

## Quick start

```bash
docker compose up -d --build
```

Verify both containers are running:

```bash
docker compose ps
```

## Environment variables

| Variable | Value | Purpose |
|---|---|---|
| `BACKEND` | `http://api:8000` | Upstream backend address |
| `PARANOIA` | `3` | CRS paranoia level (1-4). Higher = more rules = more detections, more false positives |
| `BLOCKING_PARANOIA` | `1` | Paranoia level at which blocking kicks in |
| `ANOMALY_INBOUND` | `5` | Anomaly score threshold for blocking inbound requests (critical=5, error=4, warning=3, notice=2) |
| `ANOMALY_OUTBOUND` | `4` | Anomaly score threshold for outbound response inspection |
| `MODSEC_RULE_ENGINE` | `On` | `On` = enforce, `DetectionOnly` = log but don't block |
| `MODSEC_REQ_BODY_ACCESS` | `On` | Inspect request bodies |
| `MODSEC_RESP_BODY_ACCESS` | `Off` | Skip response body inspection |
| `MODSEC_AUDIT_ENGINE` | `RelevantOnly` | Log only transactions that triggered rules |
| `MODSEC_AUDIT_LOG_FORMAT` | `JSON` | Audit log format |

Set `MODSEC_RULE_ENGINE=DetectionOnly` during initial deployment to tune rules without blocking traffic.

## Custom CRS rules

CRS ships with sane defaults, but it needs tuning for a RESTful API. The custom rules live in `custom-rules/modsecurity-override.conf` and are mounted as `REQUEST-900-METHOD-POLICY.conf` inside the container — this filename sorts before `REQUEST-901-INITIALIZATION.conf`, so the rules execute before CRS sets its defaults.

### Rule 900100 — Allow PUT/PATCH/DELETE methods

CRS defaults `tx.allowed_methods` to `GET HEAD POST OPTIONS`. Rule 911100 blocks any method not in that list with a CRITICAL score (5 points), which equals the `ANOMALY_INBOUND=5` threshold. Every PUT, PATCH, and DELETE gets a 403 out of the box.

This rule sets `tx.allowed_methods` in phase:1 before CRS init rule 901160 runs. Since 901160 only sets the default when `&TX:allowed_methods "@eq 0"`, the pre-set value is kept.

### Rule 900201 — SQLi detection in URL path

CRS SQLi rules (942100, 942130, etc.) inspect `ARGS`, `ARGS_NAMES`, cookies, and headers — but never `REQUEST_URI`. SQLi in the URL path (e.g., `/items/1' OR '1'='1`) passes completely unexamined. This rule runs `@detectSQLi` (libinjection) against `REQUEST_URI`.

### Rule 900202 — Block bodies on DELETE/GET/HEAD

CRS has no rules for unexpected request bodies on methods that shouldn't have them. This chain rule denies any request where the method is DELETE, GET, or HEAD and the body is non-empty. Uses `deny,status:403` for an immediate hard block rather than anomaly scoring (a single WARNING=3 wouldn't reach the threshold of 5).

### Why path traversal on path params is not blocked

`curl http://localhost:8080/items/../../etc/passwd` returns 404, not 403. Nginx normalizes the URI to `/etc/passwd` before ModSecurity processes the request, so `REQUEST_URI_RAW` never contains `..`. The attack is neutralized at the nginx layer — the backend never sees the traversal. CRS cannot detect what nginx already resolved.

## Testing

### CRUD operations (all should pass)

```bash
# Create
curl -s -X POST http://localhost:8080/items \
  -H "Content-Type: application/json" \
  -d '{"name": "widget", "description": "a small widget", "price": 9.99}'

# List
curl -s http://localhost:8080/items

# Get one (use the ID from the create response)
curl -s http://localhost:8080/items/1

# Update (full)
curl -s -X PUT http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "widget-v2", "description": "updated", "price": 12.99}'

# Update (partial)
curl -s -X PATCH http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"price": 14.99}'

# Delete
curl -s -o /dev/null -w "%{http_code}" -X DELETE http://localhost:8080/items/1
```

### Attack payloads (all should return 403)

```bash
# SQLi in query param
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8080/search?q=%27%20OR%201%3D1--"

# XSS in JSON body
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8080/items \
  -H "Content-Type: application/json" \
  -d '{"name": "<script>alert(1)</script>", "description": "test"}'

# Path traversal in query param
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8080/search?q=../../etc/passwd"

# SQLi via PATCH body
curl -s -o /dev/null -w "%{http_code}" -X PATCH http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"price": "1; DROP TABLE items;--"}'

# SQLi in URL path (blocked by custom rule 900201)
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8080/items/1%27%20OR%20%271%27=%271"

# DELETE with body (blocked by custom rule 900202)
curl -s -o /dev/null -w "%{http_code}" -X DELETE http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"reason": "cleanup"}'

# Path traversal on path param (neutralized by nginx, returns 404)
curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:8080/items/../../etc/passwd"
```

### Expected results summary

| Test | Status | Blocked by |
|---|---|---|
| CRUD (all methods) | 200/201/204 | Passes through |
| SQLi query param | 403 | CRS 942xxx |
| XSS in body | 403 | CRS 941xxx |
| Path traversal (query) | 403 | CRS 930xxx |
| SQLi via PATCH body | 403 | CRS 942xxx |
| SQLi in URL path | 403 | Custom rule 900201 |
| DELETE with body | 403 | Custom rule 900202 |
| Path traversal (path param) | 404 | Nginx normalization |

## Extending

### Adjust paranoia level

Lower `PARANOIA` to reduce false positives at the cost of fewer detections:

```yaml
- PARANOIA=1    # baseline rules only
- PARANOIA=2    # adds stricter SQLi, XSS, RCE detection
- PARANOIA=3    # current setting — aggressive, more false positives
```

### Add custom rules

Place `.conf` files in `custom-rules/` and mount them into the CRS rules directory. Use rule IDs below 901000 to run before CRS init, or above 990000 to run after all CRS rules.

### Switch to detection-only

```yaml
- MODSEC_RULE_ENGINE=DetectionOnly
```

Violations are logged to the audit log but requests pass through. Use this to tune rules before enabling blocking.

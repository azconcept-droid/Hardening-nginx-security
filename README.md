# Hardening-nginx-security

The owasp/modsecurity-crs image ships nginx + ModSecurity + CRS all built in, so you just point it at your backend app.

## How the image works

The container itself acts as a reverse proxy (nginx + ModSecurity inside it) sitting in front of whatever backend you give it via an env var. So the topology is:

Internet/LAN → [modsecurity-crs container:8080] → your backend app (nginx, app server, etc.)

## Test the full CRUD flow through the WAF

```
# Create
curl -X POST http://localhost:8080/items \
  -H "Content-Type: application/json" \
  -d '{"name": "widget", "description": "a small widget", "price": 9.99}'

# List
curl http://localhost:8080/items

# Get one
curl http://localhost:8080/items/1

# Update (full)
curl -X PUT http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "widget-v2", "description": "updated", "price": 12.99}'

# Update (partial)
curl -X PATCH http://localhost:8080/items/1 \
  -H "Content-Type: application/json" \
  -d '{"price": 14.99}'

# Delete
curl -X DELETE http://localhost:8080/items/1
```


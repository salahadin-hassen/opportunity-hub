# Render client-IP trust: what is known, what is not, and the support request

| | |
| --- | --- |
| Status | **Unverified for our service.** Production remains exposed to client-IP spoofing. The support request in §4 is ready and has not been sent. The founder accepted releasing before Render answers as a temporary documented risk (2026-11-04; `PRODUCTION_READINESS.md` §3.1); that does not fix it |
| Date | 2026-11-02 |
| Service | `opportunity-hub-api` (name from `render.yaml`; not checked against the live dashboard) |
| Related | Plan §F.7 S2, R1, M1-T2/T3; `ACCOUNT_LOCKOUT_THREAT_MODEL.md` |

## 1. Current production exposure

`render.yaml` starts the API with:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

With `--forwarded-allow-ips="*"`, uvicorn (0.54.0 in the local venv) trusts every peer and replaces the
ASGI client address with the **leftmost** `X-Forwarded-For` entry. The client chooses that entry, so the
per-address budget can be reset at will. A local reproduction with these exact flags confirms it
(`test_production_flags_forged_addresses_still_evade_the_address_budget_but_not_the_account`): six logins
with rotating forged entries all received 401, and none hit the address limit. Uvicorn also does not
check that the value is an IP address.

The application code (built, not deployed) can't fix this alone. Once uvicorn has rewritten the peer, the app can no
longer see the real TCP peer, so it can't check that the request came from a trusted proxy.

## 2. Facts from Render's public material (not service-specific)

| Claim | Source | Strength |
| --- | --- | --- |
| "All inbound traffic to Render web services passes through Cloudflare's global network before reaching your application." | [How Render handles DDoS attacks](https://render.com/articles/how-render-handles-ddos-attacks) (2026-04-01) | Official article; not a contract |
| The app sees the proxy's IP by default; "read the client IP from `x-forwarded-for`, not from the socket connection." | same | Official article. It does not say *which* entry |
| "Cloudflare writes [`CF-Connecting-IP`] on every request that reaches a Render web service, and it overwrites whatever the caller sent." | [Host PocketBase on Render](https://render.com/articles/host-pocketbase-on-render) (2026-07-08) | Official article |
| "Cloudflare appends to `X-Forwarded-For` rather than replacing it, so a caller who sends their own copy of the header controls the leftmost entry." | same | Official article; agrees with our analysis |
| Private-network requests "never pass through Cloudflare", so `CF-Connecting-IP` is absent | same | Official article |
| "Render's load balancer terminates SSL"; the service is "not *directly* reachable via the public internet"; same-region services can reach it over the private network | [Web Services](https://render.com/docs/web-services) | Docs |
| Inbound IP rules for web services need a Scale or Enterprise plan | [Inbound IP Rules](https://render.com/docs/inbound-ip-rules) | Docs |

**Not published anywhere we found:**

- the address ranges of the load balancer that actually connects to our container (the immediate peer);
- the exact `X-Forwarded-For` chain our process receives;
- any guarantee about `True-Client-IP`.

Community posts (a Render staff reply in the feedback forum says the first entry is the real client; users
report that client values are kept) are **not** used as evidence.

## 3. What we cannot settle without Render

1. The exact `X-Forwarded-For` chain our process receives, and how many entries Render adds.
2. Whether client-supplied entries are kept (the public articles say yes).
3. Whether `CF-Connecting-IP` is present on *every* request to `opportunity-hub-api`, including the
   custom domain `api.opportunities.sahelyon.com`, the `onrender.com` hostname and health checks.
4. Whether `CF-Connecting-IP` always overwrites a client-supplied value on our service.
5. Whether `True-Client-IP` is set, and whether it is trustworthy.
6. The CIDRs from which the immediate peer (Render's load balancer) connects to our container.
7. Whether any path reaches the container without passing through Cloudflare. Same-region services on the
   private network do so by Render's own description, and with no `CF-Connecting-IP`; are there others?

## 4. Support request (for the founder to send; nothing has been sent)

> **Subject:** Trusted client-IP headers and proxy addresses for web service `opportunity-hub-api`
>
> Hello Render team,
>
> We rate-limit login attempts per client IP in our FastAPI web service **opportunity-hub-api** (custom
> domain `api.opportunities.sahelyon.com`). To do that safely we need to know which request values Render
> guarantees, rather than relying on community posts. Could you confirm, for this service specifically:
>
> 1. The exact `X-Forwarded-For` value our process receives for a request from a client at address A that
>    sends no `X-Forwarded-For` of its own, and the value when the client sends `X-Forwarded-For: B`. Do
>    client-supplied entries stay in the header, and how many entries do Render and Cloudflare append?
> 2. Is `CF-Connecting-IP` set on every request that reaches our service: through the custom domain,
>    through the `onrender.com` hostname, and for Render's own health checks?
> 3. Does `CF-Connecting-IP` always overwrite any value the client sends?
> 4. Is `True-Client-IP` set for our service, and does Render consider it trustworthy?
> 5. From which IP ranges (CIDRs) does the immediate peer, the load balancer that opens the TCP
>    connection to our container, connect? Are these ranges stable, and where are changes announced?
> 6. Can any request reach our container without passing through Cloudflare and your load balancer? We
>    understand that same-region services on the private network can. Are there other paths, and do
>    private-network requests come from distinguishable address ranges?
> 7. Is there a documented, supported way to obtain the real client IP that you will keep stable?
>
> We won't send test traffic to production for this; a written answer is what we need. Thank you.

## 5. Future production change (requires approval after Render's answer; not implemented)

Exact values depend on the answers above, and none may be guessed.

1. **Start command**: drop `--proxy-headers --forwarded-allow-ips="*"` and run with `--no-proxy-headers`,
   so the ASGI peer is the real TCP peer. Without `--no-proxy-headers`, uvicorn still trusts loopback by
   default (`127.0.0.1,::1`). Removing the flags alone is not enough.
2. **`TRUSTED_PROXY_CIDRS`**: only ranges Render confirms in writing (answer 5).
3. **`CLIENT_IP_STRATEGY`**:
   - `header` with `CLIENT_IP_HEADER=cf-connecting-ip`, if Render confirms answers 2 and 3. The app then
     accepts the header only from a peer inside `TRUSTED_PROXY_CIDRS`, refuses lists, and treats a
     missing, malformed or proxy-address value as unavailable.
   - Otherwise `xff_rightmost` with `TRUSTED_PROXY_HOPS` set to the confirmed number of appended entries.
4. **Before the switch**, deploy with the strategy still `peer` and watch the `client_identity_degraded`
   telemetry (strategy and reason only) for unexpected reasons. The account budget keeps applying whenever
   identity is unavailable.
5. **Never**: `*` as a trusted network, a guessed CIDR, the leftmost `X-Forwarded-For` entry, or trusting a
   header from a peer outside the confirmed ranges.

**Do not simply remove the flags and keep `peer`.** With `--no-proxy-headers` and no trusted ranges, the
peer is Render's load balancer. The code can only recognise a proxy it has been told about, so it would
bucket that address, and every student would share a few load-balancer buckets: the global-bucket failure
this remediation removed. The same applies if Render's answer lists ranges incompletely.

If Render cannot give stable proxy ranges, the trusted-peer check can't be configured. The safe options are
then:

- explicitly disable the address budget, for example a new `CLIENT_IP_STRATEGY=none` that always returns
  unavailable identity (not implemented; needs approval). The account budget stays the only credential
  limit, which the threat model covers;
- or trust `CF-Connecting-IP` *without* a peer check, which is safe only if Render guarantees that no path
  bypasses Cloudflare (answer 6), and the private network is such a path. Not recommended.

# Render client-IP trust: what is known, what is not, and the support request

| | |
| --- | --- |
| Status | **Production remains exposed to client-IP spoofing.** A fix is implemented and tested locally (`render_cf_connecting_ip`), not deployed. It rests on Render's published statements, not on evidence from our service. No Render support reply is recorded. Releasing before this is resolved is a temporary accepted risk (`PRODUCTION_READINESS.md` §3.1) |
| Date | 2026-11-02, updated 2026-11-04 |
| Service | `opportunity-hub-api` (name from `render.yaml`; not checked against the live dashboard) |
| Related | Plan §F.7 S2, R1, M1-T2/T3; `ACCOUNT_LOCKOUT_THREAT_MODEL.md` |

## 1. Current production exposure

`render.yaml` starts the API with:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

With `--forwarded-allow-ips="*"`, uvicorn (0.54.0 in the local venv) trusts every peer and replaces the
ASGI client address with the **leftmost** `X-Forwarded-For` entry. The client chooses that entry, so the
per-address budget can be reset at will. It was reproduced only locally, with these exact flags, never against production
(`test_production_flags_forged_addresses_still_evade_the_address_budget_but_not_the_account`): six logins
with rotating forged entries all received 401, and none hit the address limit. Uvicorn also does not
check that the value is an IP address.

The application code (built, not deployed) can't fix this alone. Once uvicorn has rewritten the peer, the app can no
longer see the real TCP peer, so it can't check that the request came from a trusted proxy.

## 2. Evidence, by source

**Render's official material.** Published guidance about web services in general, not a statement about our service.

| Claim | Source |
| --- | --- |
| "All inbound traffic to Render web services passes through Cloudflare's global network before reaching your application." | [How Render handles DDoS attacks](https://render.com/articles/how-render-handles-ddos-attacks) (2026-04-01) |
| The app sees the proxy's address by default; "read the client IP from `x-forwarded-for`." It doesn't say which entry | same |
| Credential stuffing is "not fully covered by edge protection"; application rate limiting is ours to do | same |
| "Cloudflare writes [`CF-Connecting-IP`] on every request that reaches a Render web service, and it overwrites whatever the caller sent." | [Host PocketBase on Render](https://render.com/articles/host-pocketbase-on-render) (2026-07-08) |
| "Cloudflare appends to `X-Forwarded-For` rather than replacing it, so a caller who sends their own copy of the header controls the leftmost entry." | same |
| Private-network requests "never pass through Cloudflare", so the header is absent | same |
| A web service is reachable publicly at its `onrender.com` subdomain and custom domains, and "is not *directly* reachable via the public internet" | [Web Services](https://render.com/docs/web-services) |
| "Free web services can *send* private network requests, but they can't *receive* them." Paid web services can receive on their internal hostname. Static sites aren't on the private network. There's no per-service inbound switch; Pro workspaces can block traffic per environment | [Private Network](https://render.com/docs/private-network) |
| Custom-domain CNAMEs are created **DNS only** for verification and may optionally be switched to Proxied later (full setup needs SSL mode Full) | [Configuring Cloudflare DNS](https://render.com/docs/configure-cloudflare-dns) |
| `RENDER` is always `true` on Render. `WEB_CONCURRENCY` defaults from the plan's CPU count on services created after 2025-12-08 | [Environment variables](https://render.com/docs/environment-variables) |

**Cloudflare's documentation** ([HTTP headers](https://developers.cloudflare.com/fundamentals/reference/http-headers/)).

- `CF-Connecting-IP` holds one address and is sent from Cloudflare's edge to the origin. Cloudflare recommends it over parsing `X-Forwarded-For`.
- `True-Client-IP` is Enterprise-only and is otherwise forgeable, so we don't read it.
- Pseudo IPv4 on "Overwrite Headers" puts a Class E address in `CF-Connecting-IP` and `X-Forwarded-For`, and the real address in `CF-Connecting-IPv6`.
- Cross-zone Worker subrequests get a constant, `2a06:98c0:3600::103`. Same-zone ones reflect a value a Worker can change.
- The page doesn't state what `CF-Connecting-IP` holds across two Cloudflare layers (orange-to-orange), and we found no page that does. Treat that as unknown.

**Older community material, not decisive.** In a [feedback thread](https://feedback.render.com/features/p/send-the-correct-x-forwarded-for), Render's Anurag Goel wrote on 2021-05-28 that "we set the first IP in the list to the real client IP." A 2024 user reports Render only appends, so a client can spoof it. It is five years old, predates the articles above, and disagrees with Render's own 2026 wording. We don't rely on it.

**Our local results** (`backend/tests/test_render_client_ip.py`, synthetic headers on local servers).

- With the strategy on, forged `X-Forwarded-For` has no effect under either start command.
- Missing, malformed, duplicated, non-global or constant values give no identity, write no address bucket, and leave the account budget working.
- A direct connection can forge `CF-Connecting-IP`. That is why the strategy depends on Render's ingress.

These show how our code behaves. They don't show what Render does.

## 3. The decision and what it assumes

**Selected:** `CLIENT_IP_STRATEGY=render_cf_connecting_ip`, deliberately separate from the generic `header` strategy. It reads only `CF-Connecting-IP` (and `CF-Connecting-IPv6` when Cloudflare wrote a pseudo address). It never reads the peer or `X-Forwarded-For`, and it needs no proxy address ranges. Production refuses to start with it unless `RENDER=true`.

**It's valid only if all of these hold. None has been checked on our live service:**

| # | Assumption | Basis | Confirm by |
| --- | --- | --- | --- |
| 1 | Every public request passes through Cloudflare, which overwrites the header | Render's articles | Black-box check after deployment (§5) |
| 2 | Nothing can reach the service privately with a forged header | Free plan can't receive private traffic. `render.yaml` declares `free`, and its only other service is a static site | Dashboard: the live plan. If paid, list every service in the same workspace and region |
| 3 | The API hostname DNS mode and Cloudflare ingress | Render's edge is fronted by Cloudflare on all inbound web service traffic regardless of customer DNS mode. Render's guide recommends DNS-only (grey cloud) CNAME initially, with optional proxying (orange cloud) after TLS issuance. **Orange-cloud proxy in the customer's zone is NOT a prerequisite**, because Render's own Cloudflare layer sets `CF-Connecting-IP` on direct ingress. If orange-cloud is active, Cloudflare O2O (Orange-to-Orange) preserves the true client IP | Cloudflare dashboard: verify CNAME record points to Render and has standard SSL mode Full/Strict |
| 4 | No Worker runs on the API hostname | Nothing in the repository configures one | Cloudflare dashboard: Workers routes |

**If the service is paid (assumption 2 fails):** a service in the same workspace and region could call port 10000 directly and choose its own identity. That caller is our own code, not the internet, so this is a smaller risk than today's, but a compromised neighbour could evade the address budget. The account budget still applies. Keep such services out of this workspace, or block the traffic with a Pro environment rule. Without the header, a private caller gets no identity.

**If the record is proxied (assumption 3 fails):** don't enable the strategy until a check shows which address arrives. If it were a Cloudflare address, many students would share a bucket.

**Pseudo IPv4 and Workers are handled in code:** a Class E value uses `CF-Connecting-IPv6` (so IPv6 /64 identity survives), and only then, because a caller might set that header otherwise. Cloudflare's constant Worker address is refused. Either failure gives no identity, not a shared one.

**What remains unknown:** whether anything else can reach the container, such as a direct path to Render's load balancers (support question 6). Assumption 1 is Render's published statement, not a contract.

## 4. Support request (for the founder to send; no reply is recorded)

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

## 5. Proposed production change (requires approval; not applied)

Ship it with, or after, a release that contains this code. Earlier commits reject the new value and won't start.

**Environment:**

```
CLIENT_IP_STRATEGY=render_cf_connecting_ip
```

`TRUSTED_PROXY_CIDRS` and `CLIENT_IP_HEADER` must be unset, or the app refuses to start. Guessed address ranges are never needed.

**Start command: unchanged for this release.** `--proxy-headers --forwarded-allow-ips="*"` stays, because the strategy never
reads the address uvicorn rewrites. Tests confirm that forged `X-Forwarded-For` has no effect on identity under these flags.

**Why `--no-proxy-headers` isn't part of this release.** It would make `request.url.scheme` `http` behind Render's TLS
termination. Measured effect: Starlette's trailing-slash redirect (`/opportunities/`) would send `http://…` addresses.
The frontend calls no such paths, but the release shouldn't generate insecure URLs, and fixing that needs its own
change.

The trade-off of keeping the current flags:

| | Current flags (this release) | `--no-proxy-headers` (later) |
| --- | --- | --- |
| Rate-limit identity | Not affected: read from `CF-Connecting-IP` | Same |
| Redirect scheme | `https`, from `X-Forwarded-Proto` | `http`, until fixed |
| `scope["client"]` | Leftmost `X-Forwarded-For`, forgeable and unvalidated. Nothing in the app reads it under this strategy | Render's proxy |
| Uvicorn access log | Shows the leftmost value: a real client's address, or text a caller forged. **Don't treat it as evidence of who called**, and note it holds client addresses | Shows the proxy |
| `X-Forwarded-Proto` | A caller may influence the scheme of a redirect sent to themselves | Ignored |

So the identity flaw is addressed by the strategy, while untrustworthy access-log client values remain until a later
change. That later change must first deal with the redirect scheme, for example with `redirect_slashes=False` or an explicit
scheme, and must be tested. **Future session work (M1b) must set `Secure` on cookies explicitly and not derive it
from the scheme.**

**Order matters. Never remove these flags while the strategy is still `peer`:** the proxy's address would become every
student's bucket.

**Fallback if assumption 1 or 2 can't be accepted:** there is no explicit "no address budget" mode yet; it would be a small addition needing approval.

**Black-box check after deployment.** It needs its own authorization, because it is production traffic. Use one machine and an unused email per request:

1. Send 11 failed logins with a *different forged* `CF-Connecting-IP` each time, right after a clock minute starts. The 11th must get **429**. That shows Cloudflare overwrites the header on our service, which settles assumption 1 for the paths tried. If all get 401, the header can be forged: **turn the strategy off** and report it.
2. Wait a minute, then repeat with rotating forged `X-Forwarded-For`. The 11th must get 429.
3. Run both through the custom domain and the `onrender.com` hostname.
4. Check the logs: `client_identity_degraded` should be near zero. Many events mean the header isn't arriving, so the address budget isn't running.

Until step 1 passes on production, don't describe the issue as fixed.

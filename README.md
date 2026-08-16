# fieldblind

A small, local, entirely fictional teaching demo about **property-level authorization** — the
difference between "may this caller touch this object?" and "may this caller read or change *this
property* of it?"

It contains two containerized expense-claim APIs over one shared domain: a **secure** service that
authorizes every property by actor, and an **intentionally vulnerable** contrast service that does
not. They are the same product apart from that one boundary.

> Everything here is fixed demonstration data. There is no real employer, expense platform, person,
> merchant, amount, or credential in this project, and nothing in it talks to a real system.

## Start here

```sh
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable run --rm walkthrough
```

One command, about twenty seconds, no setup beyond Docker. It resets both services to the same fixed
state and runs every case below, printing for each one who was asking, what the object check decided,
what the property check decided, what came back, which keys the caller received, and exactly which
stored properties changed. It exits nonzero if any of that is missing.

Everything after this section explains what you just watched.

## The idea in one paragraph

Most people learn object-level authorization first: *is this row yours?* That check is necessary,
and both services here get it right. Property-level authorization is the question underneath it:
*given that the row is yours, which of its fields may you see, and which may you set?* An expense
claim is a good place to feel the difference, because the claim genuinely belongs to the employee who
filed it — and the reviewer's risk score, private note, decision, and approved amount genuinely do
not. Owning the object does not entitle you to every property on it. When an API forgets that on the
way out, callers read things they should not (**excessive data exposure**). When it forgets on the
way in, callers write things they should not (**mass assignment**, or over-posting). OWASP files both
under **API3:2023 — Broken Object Property Level Authorization**.

## BOLA versus BOPLA

| | Broken Object **Level** Authorization | Broken Object **Property** Level Authorization |
|---|---|---|
| The question it gets wrong | may this caller touch this object? | may this caller touch this *property* of it? |
| What the attacker changes | the object identifier | the property names in the request or response |
| In this demo | `uma` asking for `EXP-204` — refused by both services | `niko` reading or writing reviewer-only properties on their own claim |
| Its role here | negative control only | the entire teaching target |

`uma` gets the same generic `404` from both services. That is deliberate: it proves the vulnerable
service is broken *only* at the property boundary, so anything you see it leak or accept cannot be
blamed on a missing object check.

## The fictional scenario

The Harborlight Expense Desk holds one claim, `EXP-204`:

| Actor | Role | May do |
|---|---|---|
| `niko` | employee | read the employee view of the claim they own, and edit its `purpose` |
| `uma` | employee | nothing — they do not own `EXP-204` |
| `sol` | reviewer | read the review view, and decide the claim |

The claim's stored properties split cleanly in two:

| Employee-visible | Reviewer-only |
|---|---|
| `claim_id`, `employee_id`, `merchant`, `amount_cents`, `purpose`, `status`, `submitted_on` | `risk_score`, `reviewer_note`, `decision`, `approved_amount_cents` |

`niko` may write exactly one property: `purpose`. `sol` may write exactly two: `decision` and
`approved_amount_cents`.

## The two wrong data flows

```mermaid
flowchart TB
    subgraph shared["Both services, identical"]
        A["credential → actor<br/>(server-side only)"] --> B["object policy<br/>owner or reviewer?"]
    end

    B -->|refused| R["generic 404"]
    B -->|allowed| V["vulnerable service"]
    B -->|allowed| S["secure service"]

    subgraph vuln["INTENTIONALLY VULNERABLE — the whole object, both directions"]
        V --> V1["read: serialize every stored property"]
        V --> V2["write: bind every submitted key"]
        V1 --> V3["niko receives risk_score,<br/>reviewer_note, decision,<br/>approved_amount_cents"]
        V2 --> V4["niko sets decision = approved<br/>and approved_amount_cents = 8640"]
    end

    subgraph sec["SECURE — an explicit contract per actor, both directions"]
        S --> S1["read: employee schema<br/>names 7 properties"]
        S --> S2["write: employee schema<br/>accepts only purpose"]
        S1 --> S3["niko receives only<br/>the 7 authorized properties"]
        S2 --> S4["a body naming anything else<br/>is refused whole: generic 400,<br/>state unchanged"]
    end
```

The vulnerable paths are not exotic. They are the two most ordinary shortcuts in web development:
hand the ORM object to the serializer, and hand the request body to the model.

## What the fix actually is

**On the way out — an explicit response schema per actor.** The employee response is built by naming
its seven properties. The reviewer response is built by naming eleven. Neither is derived from the
persistence model, so a property that exists in the database cannot appear in a response unless
somebody writes its name into a contract.

**On the way in — an explicit request schema per actor, plus assignment by name.** The employee
update contract has exactly one field. Unknown, read-only, and reviewer-only keys are refused, and
the accepted value is assigned as `claim.purpose = update.purpose` — never spread, unpacked, or
iterated onto the object. The contract is chosen from the *authenticated server-side actor*, never
from anything in the request.

**Refuse the whole request, not the offending parts.** A body that mixes a legitimate `purpose` edit
with reviewer-only keys is rejected entirely: generic `400`, no partial application, canonical state
unchanged to the byte. Applying "just the allowed part" would quietly teach callers which keys work.

**Say nothing while refusing.** The `400` names no property and does not reveal whether a key was
unknown, misspelled, read-only, or reviewer-only. One structured `property_update_rejected` audit
event goes to the server log with a correlation ID, the actor, the object, the outcome, and a bounded
reason code — and no credential, body, property name, or property value.

### Things that are not property authorization

- **Filtering in the client.** The data already left the server. Anyone can read the response.
- **Not documenting a property.** Undocumented is not unreachable.
- **Hard-to-guess property names.** `internal_risk_score_v2` is one leaked response away from being
  known, and this demo's vulnerable read hands over the names for free.
- **Hidden form fields, or fields the UI does not render.** The UI is not the API.
- **Blocklisting known-dangerous keys.** The next property somebody adds will not be on the list.
  Enumerate what is *allowed*, per actor, per direction — then a new stored property is denied by
  default.

## Verify it

The host needs Docker with Compose and nothing else. Every dependency, linter, type checker, and
test runs inside one pinned image.

```sh
docker compose run --rm verify
```

That single command runs formatting, linting, strict type checking, and the whole suite: behavior
over real loopback HTTP against fresh state, the walkthrough's own assertions, static
container-hardening checks, a runtime egress check, and structural checks that fail if a contract
drifts. GitHub Actions runs the same command, unchanged.

The suite proves both halves of the claim. Security: the employee projection omits the reviewer-only
names *and* values, the mixed body is refused with state preserved byte-for-byte and exactly one
redacted audit event, and every malformed, empty, duplicate, unknown, read-only, and reviewer-only
input is refused. Preserved legitimate behavior: `niko` can still edit `purpose`, `sol` can still
read the review projection and decide the claim, and both variants still answer `uma` identically.
`tests/test_regression_matrix.py` maps every required row to the named test that proves it, and fails
if one is renamed or deleted.

## Explore it by hand

```sh
docker compose up --wait secure
```

The secure service is then on `127.0.0.1:8000` and nowhere else. Fixed demonstration credentials:

| Actor | Bearer credential |
|---|---|
| `niko` | `fictional-demo-token-niko` |
| `uma` | `fictional-demo-token-uma` |
| `sol` | `fictional-demo-token-sol` |

Read the claim as its owner — the reviewer-only property names never appear:

```sh
curl -s -H 'Authorization: Bearer fictional-demo-token-niko' \
  http://127.0.0.1:8000/claims/EXP-204
```

Read it as the reviewer — the same properties are there for the actor authorized to see them:

```sh
curl -s -H 'Authorization: Bearer fictional-demo-token-sol' \
  http://127.0.0.1:8000/claims/EXP-204
```

Try to approve your own claim by adding reviewer-only keys to an otherwise legitimate edit. The whole
request is refused, and nothing changes — not even the legitimate part:

```sh
curl -s -X PATCH -H 'Authorization: Bearer fictional-demo-token-niko' \
  -H 'Content-Type: application/json' \
  -d '{"purpose":"Team offsite ferry catering (revised)","decision":"approved","approved_amount_cents":8640}' \
  http://127.0.0.1:8000/claims/EXP-204
```

Make the edit you are actually allowed to make:

```sh
curl -s -X PATCH -H 'Authorization: Bearer fictional-demo-token-niko' \
  -H 'Content-Type: application/json' \
  -d '{"purpose":"Team offsite ferry catering (revised)"}' \
  http://127.0.0.1:8000/claims/EXP-204
```

Decide the claim as the reviewer:

```sh
curl -s -X PATCH -H 'Authorization: Bearer fictional-demo-token-sol' \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approved","approved_amount_cents":8640}' \
  http://127.0.0.1:8000/claims/EXP-204
```

Confirm the negative control — `uma` does not own this claim:

```sh
curl -s -H 'Authorization: Bearer fictional-demo-token-uma' \
  http://127.0.0.1:8000/claims/EXP-204
```

Inspect the full stored state at any point. `/demo/state/{claim_id}` and `/demo/events` are
demonstration instrumentation — they stand in for looking at the database and the log, and they take
no part in the authorization contract under test:

```sh
curl -s http://127.0.0.1:8000/demo/state/EXP-204
curl -s http://127.0.0.1:8000/demo/events
```

Put the fixture back the way it started, then shut down:

```sh
curl -s -X POST http://127.0.0.1:8000/demo/reset
docker compose down
```

## The vulnerable contrast service

> **This service is deliberately broken. It exists to be looked at, on your own machine, and nowhere
> else.**

Starting it takes two explicit actions, and neither one alone is enough — a plain
`docker compose up` never starts it, and starting it without the flag makes it refuse to boot:

```sh
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable up --wait vulnerable
```

It then listens on `127.0.0.1:8001`, with its own disposable database, so nothing it does can
contaminate the secure result. It shares the secure service's credentials, object policy, domain
model, fixture, and failure contract. It differs in exactly two places, both confined to
`src/fieldblind/vulnerable_app.py`.

**The read-side flaw — excessive data exposure.** It answers the employee's `GET` by serializing the
whole stored object generically, with no property policy at all:

```sh
curl -s -H 'Authorization: Bearer fictional-demo-token-niko' \
  http://127.0.0.1:8001/claims/EXP-204
```

The employee now has `risk_score`, `reviewer_note`, `decision`, and `approved_amount_cents` — four
properties they were never entitled to. Note what did *not* go wrong: object authorization worked
correctly. They do own this claim.

**The write-side flaw — mass assignment.** It applies client-supplied keys onto the stored object
generically:

```sh
curl -s -X PATCH -H 'Authorization: Bearer fictional-demo-token-niko' \
  -H 'Content-Type: application/json' \
  -d '{"purpose":"Team offsite ferry catering (revised)","decision":"approved","approved_amount_cents":8640}' \
  http://127.0.0.1:8001/claims/EXP-204

curl -s http://127.0.0.1:8001/demo/state/EXP-204
```

The employee just approved their own claim and set the payout. Send those exact bytes to the secure
service on port `8000` and you get a generic `400` with the state byte-for-byte unchanged.

Neither flaw is a discovery tool. There is no property enumerator, wordlist, schema fuzzer, arbitrary
target, proxy, or reusable extraction tooling anywhere in this project: the vulnerable service reaches
exactly one fictional local object through its own endpoint.

```sh
docker compose --profile vulnerable down
```

## The walkthrough in detail

```sh
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable run --rm walkthrough
```

It runs eight cases against fresh state and prints a `PASS`/`FAIL` line plus six observations for
each:

| # | Case | What it must show |
|---|---|---|
| 1 | vulnerable read disclosure | `200`, and exactly the four reviewer-only properties leak, with their fixed values |
| 2 | secure read projection | `200` with only the seven employee properties, and `sol` still gets all eleven |
| 3 | vulnerable mass assignment | `200`, and `purpose`, `decision`, `approved_amount_cents` all changed |
| 4 | secure whole-request rejection | generic `400`, exactly one audit event, canonical state unchanged to the byte |
| 5 | secure legitimate employee edit | `200`, and only `purpose` changed |
| 6 | secure legitimate reviewer decision | `200` on read and decide, and only the two decision properties changed |
| 7 | object-level control (secure) | `404` on read and write, no property data, no state change |
| 8 | object-level control (vulnerable) | identical `404` behavior |

It accepts only its enumerated modes and talks only to the Compose service names — there is no
argument that points it at another target or another object:

```sh
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable run --rm walkthrough --mode secure
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable run --rm walkthrough --mode vulnerable
```

Any other argument exits `2`, and a walkthrough with an unmet expectation exits `1`.

## Containment

Every container runs as a non-root user with all Linux capabilities dropped, `no-new-privileges`, a
read-only root filesystem, and state that exists only in tmpfs for the life of the container. The
Compose network disables IP masquerade, so the applications have no working route to any external
network — the suite proves that at runtime rather than trusting the flag. The secure service is the
only default service; everything else needs a profile. Both services publish to host loopback only.

## Repository layout

| Path | What it is |
|---|---|
| `src/fieldblind/domain.py` | fixed actors, credentials, claim fixture, and the property sets |
| `src/fieldblind/authentication.py` | server-side credential resolution |
| `src/fieldblind/object_policy.py` | the shared object-level boundary |
| `src/fieldblind/schemas.py` | actor-specific request and response contracts |
| `src/fieldblind/projections.py` | explicit claim-to-response mapping |
| `src/fieldblind/service.py` | strict parsing, validation, and transactional assignment |
| `src/fieldblind/demo_support.py` | correlation, generic failures, and the demo state/reset/events boundary |
| `src/fieldblind/secure_app.py` | the secure entry point |
| `src/fieldblind/vulnerable_app.py` | the intentionally vulnerable entry point, and only it |
| `src/fieldblind/walkthrough.py` | the fixed walkthrough runner |
| `tests/test_regression_matrix.py` | every required behavior mapped to the test that proves it |
| `tests/` | behavior, containment, and structural tests |

## Further reading

- OWASP API Security Top 10, [API3:2023 — Broken Object Property Level
  Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/)
- OWASP API Security Top 10 2023 [release
  notes](https://owasp.org/API-Security/editions/2023/en/0x04-release-notes/), which fold the earlier
  Excessive Data Exposure and Mass Assignment categories into API3:2023
- OWASP [Mass Assignment Cheat
  Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
- [CWE-213](https://cwe.mitre.org/data/definitions/213.html) — exposure of sensitive information due
  to incompatible policies
- [CWE-915](https://cwe.mitre.org/data/definitions/915.html) — improperly controlled modification of
  dynamically-determined object attributes

## Status

Educational, local-only, and not production software. It makes no outbound request, has no cloud
configuration, and supports no hosting, deployment, or production authentication.

Do not copy the `vulnerable` half into anything real: it is deliberately wrong, and that is its
entire purpose. The `secure` half is a teaching illustration of the two property-authorization
controls, not a drop-in authorization framework.

## Reporting a problem

The BOPLA behavior of the `vulnerable` service is intentional and documented — it is the
demonstration, not a bug. For anything *unintended*, please report it privately through this
repository's **Security** tab → **Report a vulnerability**, rather than opening a public issue.
[`SECURITY.md`](SECURITY.md) describes what is in and out of scope.

## License

[MIT](LICENSE) — Copyright (c) 2026 maximalfocus.

# fieldblind

A small, local, entirely fictional teaching demo about **property-level authorization** — the
difference between "may this caller touch this object?" and "may this caller read or change *this
property* of it?"

It contains two containerized expense-claim APIs over one shared domain: a **secure** service that
authorizes every property by actor, and an **intentionally vulnerable** contrast service that does
not. They are the same product apart from that one boundary.

> Everything here is fixed demonstration data. There is no real employer, expense platform, person,
> merchant, amount, or credential in this project, and nothing in it talks to a real system.

## The fictional scenario

The Harborlight Expense Desk holds one claim, `EXP-204`:

| Actor | Role | May do |
|---|---|---|
| `niko` | employee | read the employee view of the claim they own, and edit its `purpose` |
| `uma` | employee | nothing — they do not own `EXP-204` |
| `sol` | reviewer | read the review view, and decide the claim |

Four properties are reviewer-only: `risk_score`, `reviewer_note`, `decision`, and
`approved_amount_cents`. An employee owns the claim, but that does not entitle them to those
properties — not to read them, and not to set them.

## Verify it

The host needs Docker with Compose and nothing else. Every dependency, linter, type checker, and
test runs inside the pinned image.

```sh
docker compose run --rm verify
```

That single command runs formatting, linting, strict type checking, and the whole test suite,
including checks that exercise the API over real loopback HTTP against fresh, disposable state.

## Run it

```sh
docker compose up --wait secure
```

The secure service is then reachable on `127.0.0.1:8000` and nowhere else. Fixed demonstration
credentials:

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

Try to approve your own claim by adding reviewer-only keys to an otherwise legitimate edit. The
whole request is refused, and nothing changes — not even the legitimate part:

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

Inspect the full stored state at any point. `/demo/state/{claim_id}` is demonstration
instrumentation — it stands in for looking at the database, and it takes no part in the
authorization contract under test:

```sh
curl -s http://127.0.0.1:8000/demo/state/EXP-204
```

Put the fixture back the way it started:

```sh
curl -s -X POST http://127.0.0.1:8000/demo/reset
```

Shut it down:

```sh
docker compose down
```

## The vulnerable contrast service

> **This service is deliberately broken. It exists to be looked at, on your own machine, and
> nowhere else.**

Starting it takes two explicit actions, and neither one alone is enough — a plain
`docker compose up` never starts it, and starting it without the flag makes it refuse to boot:

```sh
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable up --wait vulnerable
```

It then listens on `127.0.0.1:8001`, with its own disposable database, so nothing it does can
contaminate the secure result. It shares the secure service's credentials, object policy, domain
model, fixture, and failure contract. It differs in exactly two places, both confined to
`src/fieldblind/vulnerable_app.py`:

**The read-side flaw — excessive data exposure.** It answers the employee's `GET` by serializing
the whole stored object generically, with no property policy at all. The object-level check passed,
and nothing after it asks whether *this actor* may see *this property*:

```sh
curl -s -H 'Authorization: Bearer fictional-demo-token-niko' \
  http://127.0.0.1:8001/claims/EXP-204
```

The employee now has `risk_score`, `reviewer_note`, `decision`, and `approved_amount_cents` — four
properties they were never entitled to. Note what did *not* go wrong: object authorization worked
correctly. They do own this claim. Owning an object is not the same as being entitled to every
property on it.

**The write-side flaw — mass assignment.** It applies client-supplied keys onto the stored object
generically, so "may touch this claim" silently becomes "may set anything on this claim":

```sh
curl -s -X PATCH -H 'Authorization: Bearer fictional-demo-token-niko' \
  -H 'Content-Type: application/json' \
  -d '{"purpose":"Team offsite ferry catering (revised)","decision":"approved","approved_amount_cents":8640}' \
  http://127.0.0.1:8001/claims/EXP-204

curl -s http://127.0.0.1:8001/demo/state/EXP-204
```

The employee just approved their own claim and set the payout. Send those exact bytes to the secure
service on port `8000` and you get a generic `400` with the state byte-for-byte unchanged — not even
the legitimate `purpose` edit lands.

Neither flaw is a discovery tool. There is no property enumerator, wordlist, schema fuzzer,
arbitrary target, proxy, or reusable extraction tooling anywhere in this project: the vulnerable
service reaches exactly one fictional local object through its own endpoint.

The same negative control holds in both variants — `uma`, who does not own the claim, gets the same
generic `404` from either service. The deliberate flaw here is property-level, not object-level.

```sh
docker compose --profile vulnerable down
```

## Containment

Every container in this project runs as a non-root user with all Linux capabilities dropped,
`no-new-privileges`, a read-only root filesystem, and state that exists only in tmpfs for the life
of the container. The Compose network disables IP masquerade, so the applications have no working
route to any external network — the test suite proves that at runtime rather than trusting the
flag. The secure service is the only default service, and both services publish to host loopback
only.

## How the secure service decides

Every request follows the same order, and the first two steps reveal nothing about properties:

1. **Who is this?** The actor is resolved server-side from a fixed bearer credential. A missing,
   malformed, or unknown credential gets one uniform `401`. Identity is never read from a body,
   query parameter, or role header.
2. **May they touch this object at all?** The owner and the reviewer may. Anyone else — and any
   unknown claim identifier — gets the same generic `404`.
3. **Which properties may they touch?** Only now does an actor-specific contract apply.

The property contracts are enumerated by hand:

- **Reading** uses an explicit response schema per actor. The employee schema does not mention the
  reviewer-only properties, so they cannot be serialized into an employee response by accident.
- **Writing** uses an explicit request schema per actor, and every accepted value is assigned to the
  claim by name. Unknown, read-only, and reviewer-only keys are refused — including when they arrive
  alongside a perfectly legitimate edit. The refusal is a generic `400` that names nothing, and the
  authorized part of a mixed body is *not* applied.

A refused update emits exactly one structured `property_update_rejected` audit event carrying a
correlation ID, the actor, the object, the outcome, and a bounded internal reason code — and no
credential, request body, property name, or property value.

## Repository layout

| Path | What it is |
|---|---|
| `src/fieldblind/domain.py` | fixed actors, credentials, claim fixture, and the property sets |
| `src/fieldblind/authentication.py` | server-side credential resolution |
| `src/fieldblind/object_policy.py` | the shared object-level boundary |
| `src/fieldblind/schemas.py` | actor-specific request and response contracts |
| `src/fieldblind/projections.py` | explicit claim-to-response mapping |
| `src/fieldblind/service.py` | strict parsing, validation, and transactional assignment |
| `src/fieldblind/demo_support.py` | correlation, generic failures, and the demo state/reset boundary |
| `src/fieldblind/secure_app.py` | the secure entry point |
| `src/fieldblind/vulnerable_app.py` | the intentionally vulnerable entry point, and only it |
| `tests/` | behavior tests plus structural tests that fail if a contract drifts |

## Status

Educational, local-only, and not production software. The guided walkthrough that runs every case
end to end in one command is not part of this repository yet.

# fieldblind

A small, local, entirely fictional teaching demo about **property-level authorization** — the
difference between "may this caller touch this object?" and "may this caller read or change *this
property* of it?"

This repository currently contains the **secure** service: a containerized expense-claim API that
authorizes every property by actor, on the way out and on the way in.

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

Shut it down:

```sh
docker compose down
```

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
| `src/fieldblind/secure_app.py` | the secure entry point |
| `tests/` | behavior tests plus structural tests that fail if a contract drifts |

## Status

Educational, local-only, and not production software. The intentionally vulnerable contrast service
and the guided walkthrough are not part of this repository yet.

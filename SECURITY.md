# Security policy

## What this project is

`fieldblind` is an **educational demonstration** of Broken Object Property Level Authorization
(OWASP API3:2023). It exists to be read, run locally, and learned from. It is not a library, not a
service, and not production software.

Everything in it is fixed, fictional demonstration data. There is no real employer, expense
platform, person, merchant, amount, or credential anywhere in this repository, and nothing in it
contacts a real system. The bearer credentials are literal strings like
`fictional-demo-token-niko`; they authorize nothing outside this demo.

## The vulnerable service is intentional

This repository deliberately ships **two** APIs over one shared domain:

| Service | Purpose |
|---|---|
| `secure` | authorizes every property by actor — the default, and the only service Compose starts on its own |
| `vulnerable` | the contrast: generic whole-object serialization and whole-object binding, with no property policy |

The `vulnerable` service leaks reviewer-only properties to an employee and lets an employee assign
reviewer-only properties. **That is the product, not a defect.** It is the thing the demonstration
teaches, and it is documented in the README.

Starting it requires two deliberate actions, so it can never come up by accident:

```sh
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable up --wait vulnerable
```

Both the `--profile vulnerable` selector and `ALLOW_VULNERABLE_DEMO=true` must be present; the
service refuses to start otherwise.

## Containment

Both services bind to host loopback only, on separate ports. Every container runs as a non-root
user with all Linux capabilities dropped, `no-new-privileges`, a read-only root filesystem, and
state that lives only in tmpfs for the life of the container. The Compose network disables IP
masquerade, so the applications have no working route to any external network, and the test suite
proves that at runtime rather than trusting the flag.

The only supported way to run this project is Docker with Compose, on a local machine. Do not
deploy it, host it, expose it beyond loopback, put real data in it, or reuse its code as a
production authorization pattern — the `vulnerable` half is deliberately wrong.

## Reporting a vulnerability

Please report privately through this repository's **Security** tab → **Report a vulnerability**.

Do not open a public issue for a security report.

### What is in scope

An **unintended** weakness — something that is wrong beyond the deliberate demonstration. For
example:

- a way to reach the `vulnerable` service without both opt-in actions;
- a container escape, host write, or egress from any container;
- a real credential, personal datum, or non-fictional record committed to this repository;
- the `secure` service failing its own property-authorization contract, leaking a reviewer-only
  property name or value to an employee, or accepting a forbidden property; or
- credentials or protected property values appearing in ordinary service logs or audit events.

### What is not in scope

The documented BOPLA behavior of the `vulnerable` service — its excessive data exposure and its
mass assignment — and any report that amounts to "the intentionally vulnerable service is
vulnerable." Those are the demonstration working as designed.

Because this project is educational and local-only, there is no deployed instance to attack, no
production environment, and no security patch stream. Fixes ship as ordinary commits.

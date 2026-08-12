# Architecture notes

Short notes on why the code is shaped the way it is. The whitepaper carries
the argument; this file only explains the modelling choices.

## Algorithms are registered, not submitted as code

A requestor names an algorithm from a registry rather than shipping arbitrary
code. This is a simplification of the whitepaper's model, and a deliberate
one: it makes the permission check decidable. The Databank can know, before
any plaintext is touched, which attribute will be read and how many bits may
come back.

Allowing arbitrary submitted code — the more general and more useful case —
requires static analysis of the submitted program, or an output filter strong
enough that analysis is unnecessary. The bit budget is that filter, but it
only bounds a single response. Combined with unrestricted code, a requestor
could encode arbitrary information into which of several one-bit queries it
chooses to run. This is the same cumulative-leakage problem noted below,
reached from a different direction.

## The sandbox boundary is modelled, not enforced

`SealedValue.unseal()` requires a live `SandboxContext`, and the context is
revoked on exit. This makes the boundary explicit in the type system: a code
path that reads plaintext outside the sandbox raises rather than merely
looking wrong in review.

It is not security. Any Python code can reach the underlying attribute if it
tries. Real isolation is a hardware enclave or equivalent, and the honesty of
the whole model depends on attestation — an owner needs to verify that the
sandbox is what it claims before depositing anything, and a requestor needs
the same assurance before submitting. That is stubbed in
`databank.attestation`, and it is the single largest gap between this
repository and a deployable system.

## Bit budgets are measured inside the boundary

`bitbudget.enforce` runs before the result crosses back. An over-budget
result is discarded rather than returned and regretted.

`measure_bits` refuses values whose domain it cannot bound, rather than
guessing. A date, a string, or an unbounded integer raises
`BitBudgetExceeded`. This is stricter than it needs to be and intentionally
so: the failure mode of a permissive measurement function is a silent leak.

## Consent is the default, not denial

An unrecognised request returns `CONSENT_REQUIRED` rather than `DENY`.
Denying silently would deny the owner the chance to say yes, which quietly
recreates the thing the model objects to — decisions about a person's data
being made without them.

`DENY` is reserved for requests that are structurally wrong: quota exhausted,
attribute mismatch, no record held.

## Everything is logged, including refusals

Denied and consent-pending queries produce audit entries. The pattern of who
is asking is itself information the owner is entitled to, and repeated-query
probing is only visible if the refusals are recorded too.

## The known gap

Bit-scarcity bounds a single response. It does not bound a sequence.

A requestor with an annual quota of two learns little. A requestor with an
unbounded quota, asking `age >= 18`, `age >= 19`, `age >= 20`, binary-searches
a birth year while every individual response is one bit. Quotas and the audit
trail close this in practice; the two mechanisms are complementary, not
substitutes for a proper bound.

Formalising that bound — over adaptive, correlated queries, across multiple
colluding requestors — is open work for the Technical Architecture Paper.
`bitbudget.cumulative_leakage_bound` is where it will live, and raises until
it exists.

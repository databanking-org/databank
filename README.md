# Databanking — reference implementation

A minimal, dependency-free model of the query flow described in the
Databanking whitepaper: an **Information Requestor** submits an *algorithm*
to an **Information Owner's** Databank; the algorithm runs inside a sandbox
against data the requestor never sees; a deliberately tiny answer — often a
single bit — crosses the boundary, and the transaction is logged on the
owner's statement.

> A retailer needs to know whether Alice is over 18. Under this model it
> never receives her date of birth, her age, or a margin. It receives
> `True`, and Alice sees that it asked.

Concept, case studies and the whitepaper: **[databanking.org](https://databanking.org)**

This repository is a reference model written for discussion, review and
teaching. It is **not** production software, and several of the parts that
would make it production software are deliberately left unimplemented — see
[Status](#status).

## Quickstart

```bash
git clone https://github.com/databanking-org/databank.git
cd databank
pip install -e ".[dev]"
pytest
python examples/age_check.py
```

```python
from datetime import date
from databank import Databank, Query

bank = Databank()
bank.deposit("alice", "date_of_birth", date(2007, 4, 2))
bank.grant("alice", "retailer-42", "age.over_threshold", "date_of_birth",
           quota_per_year=2)

result = bank.submit_query(Query(
    requestor_id="retailer-42",
    owner_id="alice",
    algorithm_id="age.over_threshold",
    attribute="date_of_birth",
    parameters={"threshold_years": 18, "as_of": date(2026, 6, 19)},
    as_of=date(2026, 6, 19),
))

result.value           # True
result.bits_disclosed  # 1
bank.statement("alice")  # one audit entry, visible to Alice
```

## The flow

| Step | Module | What happens |
|---|---|---|
| 1. Submission | `databank.algorithms` | The requestor names a **registered** algorithm. The registry records which attribute it reads and how many bits it may return, so the Databank can reason about the request before touching any data. |
| 2. Permission | `databank.permissions` | Checked against the owner's standing permissions, including annual quotas. An unrecognised request yields `CONSENT_REQUIRED`, not silent refusal — the owner still gets to say yes. |
| 3. Execution | `databank.sandbox` | The record is unsealed only inside an active sandbox context, and only the algorithm meets it. |
| 4. Bit-scarce output | `databank.bitbudget` | The result is measured *inside* the boundary and discarded if it exceeds the algorithm's declared budget. Values whose domain cannot be bounded are refused outright. |
| 5. Audit | `databank.audit` | Every query is logged — admitted, denied, or pending consent. |

Two design choices carry most of the argument:

**Sealed values are unreadable outside a sandbox context.** `SealedValue.unseal()`
demands a live `SandboxContext`, and the context is revoked when execution
ends. Any code path that reads a plaintext outside the boundary raises
`SealError` rather than relying on reviewer vigilance. This models the
boundary; it does not enforce it. Real isolation comes from an enclave, whose
attestation is stubbed.

**Bit budgets are checked before the result leaves.** An algorithm that tries
to return the record itself raises `BitBudgetExceeded` and nothing crosses.

## Status

Implemented and tested:

- the over-18 flow end to end, including erasure and revocation
- standing permissions with annual quotas
- per-response bit measurement and cap enforcement
- the sandbox boundary and sealed-value discipline
- the owner's audit statement

Deliberately stubbed — each raises `NotImplementedError` with a note on
*why* it is not a small job:

| Stub | Why it is open |
|---|---|
| `bitbudget.cumulative_leakage_bound` | Summing per-response bits overstates leakage for repeated identical queries and understates it for adaptively chosen thresholds. A requestor probing at 18, 19, 20… binary-searches a birth year while every single response stays within a one-bit cap. |
| `attestation.verify_quote` | Vendor-specific, and binding the quote to a reproducible build matters more than the signature check — an attested enclave running unaudited code proves little. |
| `audit.seal_chain` | A hash chain alone lets an owner detect tampering only if they retained an earlier root; needs owner-held checkpoints or a transparency log. |
| `settlement.access_fee`, `settlement.owner_share` | Policy parameters, not engineering ones. Per-bit pricing would make cheap queries about sensitive attributes attractive — a distributional choice for legislation, not for this repository. |
| `storage.persist` | Durable storage raises residency, retention and succession questions that a reference implementation should not answer by accident. |
| `income.*`, `location.*`, `health.*` algorithms | Registered so the shape is visible. `location.within_region` in particular should not ship before cumulative-leakage accounting exists: repeated queries over shrinking regions binary-search an address. |

The stubs are covered by tests asserting that they fail loudly. A stub that
silently returns a default is worse than no stub — it invites someone to
build on a number nobody chose.

## Relationship to the papers

The whitepaper sets out the model and the policy case. A forthcoming
Technical Architecture Paper takes up the questions this repository marks as
open, cumulative leakage bounds in particular. Nothing here should be read as
settling them.

## Contributing

Issues and pull requests welcome, especially: attacks on the bit-scarcity
argument, additional query types with an honest account of what they leak,
and prior art this should cite.

## Licence

MIT — see [LICENSE](LICENSE).

## Contact

<contact@databanking.org> · [databanking.org](https://databanking.org)

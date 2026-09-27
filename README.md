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
python examples/erasure_request.py
python examples/leakage_budget.py
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
| 2a. Leakage budget | `databank.leakage` | If the Databank has one, the per-datum quota shared by all requestors is checked next. A denied query consumes nothing. |
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

## Repeated queries: the leakage budget

One bit per answer does not stop a requestor from asking many questions.
`age >= 18` evaluated on successive dates, halving the interval each time,
recovers a birthday in about nine answers once the year is known.
`examples/leakage_budget.py` shows it happening, and then stops it.

The model supplies the missing constraint. Only a Databank may store
attributable data; only attested requestors may query, and every query is
logged; and a requestor may hold an answer only for a short retention period
`tau`, long enough to act on it. Bisection needs the answers combined, and
therefore held. So the Databank caps queries per datum:

- the quota attaches to the **datum, not the requestor**, and counts all
  requestors together, so colluding requestors gain nothing;
- **correlated attributes share one quota** (`date_of_birth`, `age`,
  `school_year` are one group);
- each requestor's **share is smaller than the daily quota**, so no single
  requestor can exhaust the datum and block legitimate checks;
- within any retention window at most `k − 1` queries run, where
  `k = ceil(log2(R / r))` is the number of answers needed to resolve a
  realistic prior range `R` to resolution `r`, which gives a maximum request
  frequency `f_max = (k − 1) / tau`;
- designated requestors may be **exempt**, and are still logged.

The budget renews: what a requestor may hold expires after `tau`, unlike a
differential-privacy budget, which is spent for good. The parameter values in
`adult_birth_date_policy()` are illustrative; choosing real ones is open.

```python
from databank import Databank
from databank.leakage import LeakageBudget, adult_birth_date_policy

bank = Databank(leakage=LeakageBudget([adult_birth_date_policy()]))
```

## Erasure without disclosure

`python examples/erasure_request.py` runs the second worked example: Alice
asks a data broker to erase her record without telling it who she is.

The inversion is worth noticing. Every other algorithm here answers a question
about the *owner's* data. This one answers a question about the *requestor's*
data, using the owner's only as the yardstick — so the owner discloses nothing
in order to be forgotten, which is the entire difficulty with every erasure
route that exists today, GDPR subject requests and California's DROP included.

The example exists mainly to be honest about what breaks it: **typos**. Broker
records misspell names, abbreviate addresses, and go stale. Erasure that
matches only exactly is erasure defeated by the controller's own clerical
error — and defeated silently, because "we mistyped your name" and "we do not
hold you" produce the same answer. So the mechanism has to tolerate error, and
tolerance is charged twice:

| Dial | Turned one way | Turned the other |
|---|---|---|
| **Fingerprint** — how coarse the broadcast digest is | Coarse: survives typos, reveals little, but admits a large candidate set, so the broker runs many one-bit oracle queries | Fine: cheap and few queries, but a typo'd record never enters the candidate set, and the digest approaches an identifier — DROP's failing, since a deterministic hash of an email is reversed by hashing guesses |
| **Threshold** — how close counts as a match | Loose: forgives the typo, and deletes a stranger's record, unattributably, with nobody able to detect it happened | Tight: protects the stranger, and leaves the Owner's record in place |

Running the example prints the measurement that matters: the worst true match
scores 0.880, the best false one 0.835. The threshold has to fall inside a gap
0.045 wide, and no amount of engineering widens it — a person one letter from
you is genuinely almost you, to any matcher not permitted to look properly.

Which is why `matching.calibrate_threshold` is a stub rather than a formula.
The two errors fall on different people: a false negative costs the Owner her
right to erasure, a false positive destroys the record of someone who asked for
nothing, is never told, and has no obvious remedy. There is an argument for
setting it loose, and it is a legal one — the typo is the controller's, and a
controller who cannot reliably tell which record is whose has trouble
demonstrating the accuracy GDPR Art. 5(1)(d) requires or the accountability
Art. 5(2) requires. That is a position for the whitepaper to take, not for a
function to take by returning a number.

Two refusals in the flow are design rather than validation, and neither is
sufficient:

- **The requestor may not choose the threshold.** One free parameter turns a
  sequence of one-bit answers into a similarity score by bisection.
- **Candidates must lie in the broadcast fingerprint band**, or the query is a
  general-purpose identity oracle.

Both are logged as `DENY` on the owner's statement rather than raised to the
requestor — a refused probe should reach the party who does not already know
about it — and both consume quota, because free probing is unbounded probing.
Even so, a broker can vary a spelling *within* the band and watch for the
answer to flip, recovering the true string from the shape of the threshold
ball. That is the age-threshold binary search wearing a different hat, and it
is bounded by quota, fee and audit trail, and by a `databank.leakage` policy
once one is defined for identity fields. None is yet: the realistic prior
range of a name has no obvious unit.

The example also prints the failure with no defence at all: a record holding
Alice's name, spelt correctly, at the address she left in 2019. The fingerprint
keys on the postcode district, so a house move puts it permanently out of
reach. It is never selected, never queried, and never appears on her statement.
She cannot distinguish it from not being held.

## Status

Implemented and tested:

- the over-18 flow end to end, including erasure and revocation
- the erasure-without-disclosure flow: canonicalisation, lossy fingerprinting,
  candidate selection, one-bit matching, and both refusals
- standing permissions with annual quotas
- the retention-bounded leakage budget: per-datum quotas shared by all
  requestors, grouped correlated attributes, per-requestor shares, sliding
  retention windows, and exemptions
- per-response bit measurement and cap enforcement
- the sandbox boundary and sealed-value discipline
- algorithm refusals, logged as `DENY` on the owner's statement
- the owner's audit statement

Deliberately stubbed — each raises `NotImplementedError` with a note on
*why* it is not a small job:

| Stub | Why it is open |
|---|---|
| `bitbudget.cumulative_leakage_bound` | The *bound* is enforced by `databank.leakage`. This is the complementary *estimate* of what a given audit sequence actually disclosed, for review after the fact. Summing per-response bits overstates leakage for repeated identical queries and understates it for adaptively chosen thresholds. |
| `attestation.verify_quote` | Vendor-specific, and binding the quote to a reproducible build matters more than the signature check — an attested enclave running unaudited code proves little. |
| `audit.seal_chain` | A hash chain alone lets an owner detect tampering only if they retained an earlier root; needs owner-held checkpoints or a transparency log. |
| `settlement.access_fee`, `settlement.owner_share` | Policy parameters, not engineering ones. Per-bit pricing would make cheap queries about sensitive attributes attractive — a distributional choice for legislation, not for this repository. |
| `storage.persist` | Durable storage raises residency, retention and succession questions that a reference implementation should not answer by accident. |
| `matching.encode_for_private_match`, `matching.private_match` | Bloom-filter record linkage is the obvious construction and has been repeatedly broken — by frequency and pattern-mining cryptanalysis, and by graph matching that needs far less prior knowledge. Both need an accumulated corpus of encodings to work, which an erasure broadcast supplies over time, drawn from exactly the population that asked to be forgotten. Shipping an encoding that *looks* private would undermine the one claim the erasure case rests on. `matching.similarity` is plaintext edit distance and says so. |
| `matching.calibrate_threshold` | The two errors fall on different people, and one of them is not party to the transaction. An allocation of rights, not a calibration. |
| `matching.erasure_receipt` | The Databank can log that a match was answered; it cannot see whether the company then deleted anything, and a company's attestation about its own systems is worth whatever the penalty for lying is worth. |
| `income.*`, `location.*`, `health.*` algorithms | Registered so the shape is visible. `location.within_region` in particular should not ship without a leakage policy for `home_address`: repeated queries over shrinking regions binary-search an address. |

The stubs are covered by tests asserting that they fail loudly. A stub that
silently returns a default is worse than no stub — it invites someone to
build on a number nobody chose.

Four of them have issues open —
[#1](https://github.com/databanking-org/databank/issues/1) cumulative leakage
(the bound is implemented; the after-the-fact estimate remains open),
[#2](https://github.com/databanking-org/databank/issues/2) attestation,
[#4](https://github.com/databanking-org/databank/issues/4) tamper-evident audit,
[#5](https://github.com/databanking-org/databank/issues/5) privacy-preserving
identity matching — alongside
[#3](https://github.com/databanking-org/databank/issues/3), a usability gap in
the consent flow rather than a stub.

The rest are deliberately untracked. `settlement.access_fee`,
`settlement.owner_share`, `storage.persist` and `matching.calibrate_threshold`
are policy choices about pricing, residency, retention and the allocation of a
controller's data-quality failure; the right forum for them is the whitepaper
and, eventually, legislation — not a pull request. `matching.erasure_receipt`
is the same: deletion is enforced by penalty, not by protocol. The placeholder
`income.*`, `location.*` and `health.*` algorithms wait on leakage policies
for their own attributes, so they follow #1 rather than standing on their own.

## Relationship to the papers

The whitepaper sets out the model and the policy case. The Technical
Architecture Paper, in preparation, takes up the questions this repository
marks as open. Its retention-bounded leakage budget is what
`databank.leakage` implements; the parameter values it leaves open are left
open here too. Nothing else here should be read as settling the questions
the paper treats as open.

## Contributing

Issues and pull requests welcome, especially: attacks on the bit-scarcity
argument, additional query types with an honest account of what they leak,
and prior art this should cite.

## Licence

MIT — see [LICENSE](LICENSE).

## Contact

<contact@databanking.org> · [databanking.org](https://databanking.org)

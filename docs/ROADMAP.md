# Roadmap

Ordered roughly by how much each unblocks.

## Near term

- **Cumulative leakage accounting.** Replace the stub with a defensible bound
  over sequences of queries. Prerequisite for the location and income
  algorithms, and the most substantive open problem here.
- **Tamper-evident audit.** Hash chain plus owner-held checkpoints, or
  publication to a transparency log.
- **Consent flow.** A `CONSENT_REQUIRED` result currently ends the story. It
  should be resumable: forward the request to the owner, and let an answer
  reopen the query without the requestor resubmitting.

## Medium term

- **Attestation.** Verify a real enclave quote against a reproducible build
  of the sandbox, on at least one platform.
- **Arbitrary submitted algorithms**, with static analysis sufficient to
  bound what they read and return.
- **Persistence**, once residency and retention policy is settled rather than
  assumed.

## Not planned here

- Settlement and fee splits. Statutory, jurisdiction-specific, and not the
  reference implementation's to invent.
- Anything resembling a production Databank. This repository exists to make
  the model concrete enough to attack.

Suggestions and attacks: <contact@databanking.org>, or open an issue.

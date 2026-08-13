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
- **Privacy-preserving identity matching.** `matching.similarity` compares
  plaintext and claims nothing else, which is fine inside the sandbox and
  useless for a deployment where the company will not hand over its record
  either. The obvious construction — Bloom-filter encodings compared by Dice
  coefficient — has been broken repeatedly by frequency alignment, so this
  needs a threat model and a citation before it needs code.
- **Silent non-matches.** An owner cannot currently distinguish "the broker
  mistyped my name", "the broker holds my old address" and "the broker does
  not hold me". All three produce nothing on her statement. Whether that gap
  can be closed without turning the fingerprint into an identifier is open,
  and it may be the more important of the two erasure problems: an unusable
  right that reports success is worse than one that reports failure.

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
- The match threshold. Its two errors fall on different people, one of whom
  is not party to the transaction and never learns of it. Where it sits
  decides who bears the cost of a controller's own bad data, which is a
  question for legislation and for the whitepaper.
- Deletion receipts. The protocol's contribution ends at not leaking the data
  on the way in; whether a company actually deletes is enforced by penalty.
- Anything resembling a production Databank. This repository exists to make
  the model concrete enough to attack.

Suggestions and attacks: <contact@databanking.org>, or open an issue.

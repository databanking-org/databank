# Contributing

This is a reference model for a policy proposal, so the most valuable
contributions are arguments, not features.

Especially welcome:

- **Attacks on the bit-scarcity argument.** If you can reconstruct more than
  the model claims is possible, that is the most useful issue you can open.
- **Prior art.** Existing systems, papers or patents this should cite. The
  proposal is stronger for acknowledging what already exists.
- **Query types**, accompanied by an honest account of what they leak over
  repeated use.

## Ground rules

- No dependencies beyond the standard library in `src/`. `pytest` for tests.
- Stubs raise `NotImplementedError` with a docstring explaining why the
  problem is not small. Do not replace a stub with a plausible default.
- New algorithms declare their attribute and maximum output bits at
  registration.
- Tests accompany behaviour changes.

```bash
pip install -e ".[dev]"
pytest -q
```

## Scope

Discussion of the policy proposal itself belongs at
<contact@databanking.org> or with the papers, not in the issue tracker —
though an issue is the right place if the code and the papers disagree.

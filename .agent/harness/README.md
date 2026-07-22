# P0 Contract Harness

## Owners

```text
docs/contracts/MAIN_CONTRACT_MATRIX.md
  owns long-term stable system semantics

docs/superpowers/plans/2026-07-21-p0-contract-traceability-matrix.md
  owns current P0 selection, task and selector mapping

.agent/harness/contracts/p0-contracts.json
  is a generated executable mirror, never an independent editable truth

.agent/harness/runs/<run-id>/
  owns evidence for one code/config/input execution
```

The generation direction is one-way: P0 Markdown to the contract mirror to typed global bindings. Scripts never write either Markdown Owner.

`fixture` is the default mode and rejects declared network-enabled Provider configuration. `live` requires an explicit mode and remains subject to Provider policy. A task receipt reports only the selected task; it cannot claim a formal P0 verdict. Only a `full-p0` receipt may do so.

Every run records code, config, input, contract-definition, and start-time status-projection identities before selectors execute. Completed run directories are read-only. Mutable pointers and status-only projections are informational and never replace a literal run directory as evidence.

Binding buckets remain distinct: primary means direct enforcement, while related business and related implementation bindings provide support or boundary evidence only.

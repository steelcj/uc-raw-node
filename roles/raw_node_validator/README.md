# raw_node_validator

Checks the `RN-*` clauses of the raw node contract on a built node, the same way no matter how the node was built. Called by `build.yml` after `wait_phone_home.yml`, with the node's address and SSH host keys in `raw_node_report_*`.

## Status

Not implemented. `tasks/main.yml` is a placeholder that fails with "not implemented yet", so `build.yml` cannot confirm a node yet. The test-only override `raw_node_test_skip_validation: true`, set by `tests/build.yml`, skips the check so the rest of the pipeline can be tested; it is not a feature and must never be set outside tests.

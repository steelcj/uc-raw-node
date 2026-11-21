The branch isn't on GitHub yet, so the PR command in your Claude Code session hasn't run. Opening the PR now is fine. Here's what I'd do before or alongside it, and my answers to the three decisions.

### The three decisions

- **Teardown in a failed build: approve.** The new rule is safer than my default and closer to the design's intent. A failed build cleans up only what that run created, and `destroy.yml` uses the ownership keys to delete a node you're deliberately removing. My default had a real hole. If a build stopped before launching anything, it could still have deleted an older node of yours with the same hostname, because that node carries the keys. Good catch. This goes into layout design v0.1.9.
- **Contract input as extra vars: approve.** That's what the design's own commands assume, and the `raw_node_input_*` copies protect against the extra-vars precedence trap. Reading a file only when `raw_node_input_file` is given is a reasonable way to keep the test fixtures working.
- **Attempt state when nothing was built: change it.** `destroyed` is misleading there. Someone running `destroy.yml` later, or the orchestration controller, would think a node existed. Leaving it at `failed` doesn't work either, because `failed` is also the in-between state when failure handling itself crashes partway. I'd add a sixth state, `aborted`, meaning the build failed before anything was created and there's nothing to tear down. That's a design change, so I'd put it in v0.1.9 and make it a small follow-up commit rather than redo this branch. If you'd rather, Claude Code can add it to the PR now, since it's only a few lines in `handle_failure.yml` plus a test check.

### Before you push

- **Tag `main` first.** `v0.1.0` isn't on the remote yet. `main` is still at `3c1cf79`, so the tag commands I gave earlier will still mark the layout before the migration.
- **Commit the kickoff to the branch.** Commit v0.1.3 under its timestamped name in `en/docs/sessions/`, along with the removal of v0.1.1. Then the PR includes the instructions that drove it, and the session record's references to the kickoff point at a file in the repo.
- **Update the README requirements.** It should say tests ran on ansible-core 2.21.6 and not claim 2.22. Testing on 2.21 is actually reassuring: that's the version where errors raised by an include stop going to the rescue section, and the rescue path still passed.

### In the PR description

Link the session record. List the three decisions with your answers, and the two untested paths: the report timeout, and `git check-ignore` exiting with 128. I wouldn't hold the merge for those two; they can go on the follow-up list.

### After merge

- Run `ansible-lint` once (`pipx install ansible-lint`), since the session couldn't.
- Tag the merge commit `v0.2.0`.
- Next is the real payload. Pinning down the `RN-*` clauses for `raw-node-firstboot` will also settle the empty SSH host keys, since the payload will have to install the SSH server on the default Debian 13 image.

Want me to write layout design v0.1.9 from the session record once the branch is pushed? It would remove the Migration section, add the teardown rule, `raw_node_root`, the input handling and the `aborted` state, and trim the Changes section.

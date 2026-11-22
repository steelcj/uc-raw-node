# Kickoff: A Working Raw Node on Incus Debian 13

- **Version:** 0.2.0
- **Date:** 2026-11-22
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose

This is the kickoff prompt for a Claude Code session that makes this command build a Debian 13 Incus container that meets raw node contract 0.3.1:

```sh
ansible-playbook build.yml \
  -e @$HOME/.secrets/uc-raw-node/inputs/deb13-ic-01.yml \
  -e target_platform=incus_container_default \
  -e raw_node_incus_project=uc-raw-node-test
```

Paste everything under "Prompt" into Claude Code, started at the repository root on an up-to-date `main`.

## Prompt

You are working in uc-raw-node, the raw node controller, at `v0.3.0` or later. The pipeline works end to end, but `tasks/payload.yml` and `roles/raw_node_validator` are placeholders, so `build.yml` stops before launching anything. Your job is to replace them, in the seven steps below, so that the command above ends with the attempt `confirmed` and a running container that meets the contract.

### The contract is the only link

uc-raw-node meets the raw node contract on its own. Build everything from the contract text. Do not copy files from, depend on, or refer to uc-ventoy or any other producer. A node from uc-raw-node and a node from another producer are interchangeable because both meet the contract, not because they share code.

### Read first

- The contract: `https://github.com/steelcj/uc-contracts`, `en/docs/node-onboarding-pipeline/1-raw-node-egress/uc-raw-node-contract.md` at commit `3f90d9e` (version 0.3.1). Clone it read-only into a scratch directory outside this repository. Its clauses, shared parameters, confirmation fields and value types are your specification.
- `en/docs/incus/spike-incus-container-validation-v0.2.19.md`, for what was learned about meeting the clauses in an unprivileged Incus container, especially Foomuuri, RN-FW-03 and RN-FW-04. Use its findings, not its files.
- `en/docs/design/raw-node-controller-layout-design-v0.1.11.md`, `README.md`, `en/docs/sessions/README.md`, and everything under `tasks/`, `roles/`, `tests/` and `tools/`.

### Ground rules

- Work on a new branch from `main`, `raw-node-payload`. Commit at the end of each step, with a message naming the step. Do not push or open a pull request unless I ask.
- ansible-core 2.21.6, fully qualified module names, ansible-core modules only.
- Keep the layout design's rules: `no_log: true` on anything that reads, renders or delivers the payload or refers to the secrets path; the masked-task rule for failure reasons; no hashes, keys or tokens in output, records, reports, logs or failure messages. Extend `tools/check_variables.py`'s secret patterns to new variables rather than adding `ci-allow` exceptions.
- After each step, run `tools/check.sh` in full and fix what fails.
- Markdown follows the house style: commas rather than em dashes, no heading numbers, no horizontal rules, no hard line wraps in prose, subsections as headings rather than bolded lead-ins.
- Create the session record at the start (see the last step) and keep adding to it.

### Decisions already made

- **Templates are code, rendered values are secrets.** Every template lives in the repository under `templates/` and holds no secret, not even an example value. Rendered files that carry contract values land only in `~/.secrets/uc-raw-node/<hostname>/` (the existing `raw_node_secrets_dir`), with mode `0600`, and are deleted when the build ends, whatever its outcome.
- **The payload is one self-contained script,** `raw-node-adopt`, rendered from `templates/raw-node-adopt.sh.j2`. The node-side files it installs are uc-raw-node's own templates under `templates/raw-node/`, embedded into the script with quoted heredocs (`<<'RAW_NODE_EOF'`). Because it is one file, the transport's existing push and run deliver it unchanged.
- **The node reports `contract: "0.3.1"` and `baseline: "uc-raw-node/0.4.0"`.** Put the baseline in one variable in `vars/defaults.yml`, `raw_node_baseline_version`, and the contract version in `raw_node_contract_version`.
- **The firewall manager is Foomuuri,** as uc-raw-node's own choice, which the contract allows.
- **The first-boot report is written in Python 3,** which the payload installs. The confirmation's quoting rules and field types are easier to get right with Python's standard library than in shell. The report must use only the standard library.

### Step 1: The full node definition

- Extend `load_input.yml` with the contract's optional shared parameters, `ssh_port` (default 22, an integer from 1 to 65535) and `ssh_sources` (default empty, meaning any; a list of IPv4 or IPv6 addresses or networks, host bits refused), and the optional `password_batch` (letters, digits, `.`, `-`, `_`, at most 64). Put all three into `raw_node_input` with their defaults.
- Refuse a `hostname` ending in `-vt`, and refuse any field value containing a single quote or a newline, so every value can sit safely inside single quotes in the rendered script. Crypt hashes and OpenSSH keys never contain either.
- `hostname`, `initial_username`, `ssh_port` and `ssh_sources` are public. The two hashes, the key and `password_batch` are not.

Checks: input tests for a valid definition using all three optional fields, and one failing case per rule.

### Step 2: The payload template

Write `templates/raw-node-adopt.sh.j2` and the node-side templates under `templates/raw-node/`. Run as root on a fresh `images:debian/13` instance, the script does the following, each as a numbered step that, if it fails, prints only `raw-node-adopt: step <n> <name> failed (exit <code>)`:

- **Block service starts** with `/usr/sbin/policy-rc.d` exiting 101 while packages install, then remove it. Without this, Debian starts `ssh` before its configuration exists and `foomuuri` before its rules exist.
- **Install** `openssh-server`, `sudo`, `python3`, `nftables` and `foomuuri` with `apt-get update` then `DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends`.
- **Root password:** `printf 'root:%s\n' '<hash>' | chpasswd -e`. `printf` is a shell built-in, so the hash never appears in a process's arguments.
- **Initial user:** `useradd -m -s /bin/bash -G sudo`, its hash through `chpasswd -e` the same way, `.ssh/` mode `0700` and `authorized_keys` mode `0600` holding only `ssh_public_key`, both owned by the user (RN-ACC-01, RN-ACC-02).
- **SSH:** `/etc/ssh/sshd_config.d/10-raw-node-auth.conf` with `PermitRootLogin no`, `PubkeyAuthentication yes`, `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitEmptyPasswords no` (RN-SSH-03, RN-ACC-05), and `20-raw-node-port.conf` with `Port <ssh_port>` (RN-SSH-01). Check with `sshd -T` in Step 7 that the drop-ins win over the stock file.
- **Firewall:** `/etc/foomuuri/00-raw-node.conf`, rendered from `templates/raw-node/00-raw-node.conf.j2` with `ssh_port` and `ssh_sources`: inbound SSH from `ssh_sources` (or any), DHCP and DHCPv6 replies, ping and the ICMP and ICMPv6 networking needs; everything outbound; nothing forwarded (RN-FW-03). The container's interface is `eth0`, so the public zone must cover `eth*`. Mask `nftables.service`, whose stop action flushes the whole ruleset (RN-FW-02).
- **Report:** `/usr/local/sbin/raw-node-report` (from `templates/raw-node/raw-node-report.py`) prints the confirmation, keyed by the hostname, with exactly the contract's fields, each measured on the node when it runs: `contract`, `baseline` (both read from `/etc/raw-node/raw-node.conf`), `timestamp`, `machine_id`, `user`, `sudo`, `sudo_nopasswd` (non-comment lines of every sudoers file), `ssh_port` and `ssh_password_auth` (from `sshd -T`, or `sshd -G` if `-T` fails), `ssh_host_keys` (`ssh-keygen -l` on each host public key), `firewall`, `firewall_active`, `python`, and `interfaces` (every interface except loopback, with its permanent MAC, state, default routes and addresses, global IPv6 only). Every string value is written in double quotes, as the contract advises, and the booleans and `ssh_port` unquoted. If any field cannot be measured, it exits non-zero and prints nothing on standard output.
- **First boot:** `/usr/local/sbin/raw-node-firstboot` and `raw-node-firstboot.service`. The unit runs once at boot, after the network is online and after `ssh-keygen` has produced the host keys, and only while `/var/lib/raw-node/confirmation.yml` does not exist. The script writes the report's output to that file, mode `0644`, readable by the initial user (RN-REP-01). If the report fails, it writes nothing, so the unit runs again at the next boot.
- **Node settings:** `/etc/raw-node/raw-node.conf`, mode `0644`, with `RAW_NODE_USER`, `RAW_NODE_CONTRACT`, `RAW_NODE_BASELINE`, and `RAW_NODE_PASSWORD_BATCH` when set.
- **Services:** enable `ssh.service`, `foomuuri.service` and `raw-node-firstboot.service`. Start nothing. The restart in Step 4 brings them up in boot order.
- **Clean up:** the script deletes itself on exit, success or failure (`trap`).

The script never prints a contract value, never runs with `set -x`, and holds every value in single quotes. Assert in a test that the heredoc delimiter appears nowhere in the embedded files.

Checks: render the template for the test fixture with a test playbook. Check the result with `sh -n`, and with `shellcheck` if it is installed. Run the report's Python with `python3 -m py_compile`, and test it on the controller host against a fake root directory if you can, as uc-raw-node's own unit test.

### Step 3: Render the payload

Replace the placeholder in `tasks/payload.yml` with one `ansible.builtin.template` task rendering `raw-node-adopt.sh.j2` to `{{ raw_node_secrets_dir }}/{{ raw_node_hostname }}/raw-node-adopt`, mode `0600`, `no_log: true`, keeping the masked-task rule for its failure. Keep `raw_node_test_payload_file` for the stand-in tests.

### Step 4: Restart and pull the confirmation

- In `roles/raw_node_transport_incus_exec/tasks/main.yml`, after the existing push, run and removal of the payload, restart the instance with `incus restart`. On that boot the firewall comes up before the network (RN-FW-04) and the first-boot unit writes the confirmation.
- Add `tasks/report.yml` to the transport. It waits, bounded by the `raw_node_report_timeout` that `wait_phone_home.yml` passes, until `/var/lib/raw-node/confirmation.yml` exists in the instance, then pulls it with `incus file pull` to `{{ raw_node_reports_dir }}/{{ raw_node_hostname }}/confirmation.yml`, mode `0644`, and sets `raw_node_transport_report` (`found`, `file`, `waited`). It does not fail on timeout; the caller judges.
- `wait_phone_home.yml` calls the transport with `tasks_from: report` instead of `address`, and sets `raw_node_report_*` from the pulled confirmation. Keep writing `reports/<hostname>/report.yml`. On timeout, `no_report` as before.
- Extend `tests/bin/incus` with `restart` and `file pull`, serving a fixture confirmation, `tests/fixtures/confirmation.yml`, in the contract's format. Include values a YAML 1.1 reader gets wrong: a `machine_id` of digits only with a leading zero, a MAC address of decimal digits and colons, a timestamp, and an IPv6 address of decimal digits and colons, each quoted, plus one copy left unquoted to prove the reader handles both.

### Step 5: Read the confirmation and validate

- Write `filter_plugins/raw_node_confirmation.py`, a filter that parses the confirmation with PyYAML's `BaseLoader`, so every value is a string, converts only the six booleans and `ssh_port`, and raises an error naming the field for a missing field or bad type, without echoing values. Unit-test it in `tests/unit/`, run by `tools/check.sh`.
- Replace the placeholder `raw_node_validator` with checks against the contract, in three task files. Every failed check names its clause in `raw_node_failure_reason`.
  - **The confirmation:** its only key is the hostname, every field is present with the right type, `contract` is `0.3.1`, `user` is `initial_username`, `sudo` is true, `sudo_nopasswd` and `ssh_password_auth` are false, `ssh_port` matches the input, `firewall_active` is true, and `ssh_host_keys` is not empty.
  - **Inside the node, through `incus exec`:** RN-NET-01, RN-ACC-01, RN-ACC-05, RN-ACC-07, RN-SSH-01, RN-SSH-03, RN-FW-01, RN-FW-02, RN-FW-04 (activation times in this boot, the firewall before `network-pre.target` before the network service, which you find rather than assume), RN-REP-01, and each host key's fingerprint present in `ssh_host_keys`.
  - **From the controller host:** `ssh-keyscan` of the node's first IPv4 address must give exactly the fingerprints in `ssh_host_keys`. Every SSH command then uses a known-hosts file written from those keys under `reports/<hostname>/`, never the operator's own. Key login as `initial_username` succeeds (RN-ACC-02, RN-SSH-02). Password and keyboard-interactive logins for it and for root are refused without a prompt (RN-SSH-03). A `python3 -m http.server` listener started inside with `systemd-run` on a closed port answers from inside but not from the controller host, while SSH and ping do (RN-FW-03).
  - **By proxy, since the controller never holds the initial password:** RN-ACC-04 (`sudo -l -U` grants root, RN-ACC-07 holds, `passwd -S` reports `P`) and RN-ACC-06 (`passwd -S` reports `P`, a console getty is enabled). RN-ACC-08 is met by procedure.
- The validator logs in with the operator's SSH agent and default keys, or `-e raw_node_validator_ssh_key=<path>`. It never copies or stores a private key.
- Write `reports/<hostname>/validation.yml`, one entry per clause: `met`, `checked_by_proxy` or `by_procedure`, with the check that decided it.

Checks: the confirmation checks run against the fixture and one failing copy per rule, without a node.

### Step 6: Hand off

`write_confirmation.yml` copies `reports/<hostname>/confirmation.yml` byte for byte to `records/<hostname>/confirmation.yml`, then sets the attempt `confirmed` and deletes the node's secrets directory, as before. The controller adds nothing to the node's confirmation.

Set `incus_container_default`'s `firewall_clause` to `applies` in `registry/base.yml`, and update its notes. Leave its `status` alone.

Update the stand-in scenarios. `placeholders` no longer exists; replace it with a payload that fails at a given step, which must end `destroyed` with a reason naming the step and no output.

### Step 7: Prove it on the real Incus host

Run only if `incus info` succeeds, in the existing `uc-raw-node-test` project.

- Make a throwaway node definition under `artifacts/acceptance/`, mode `0600`: hostname `rn-accept-01`, a fresh `ssh-keygen -t ed25519 -N ''` key pair beside it, and yescrypt hashes of two random 24-character passwords, which you save in a `0600` file there for me. Never print them.
- Run the command at the top of this kickoff with that definition and `-e raw_node_validator_ssh_key=` pointing at the throwaway key. It must end `confirmed`, with every clause in `validation.yml` `met` except the two by proxy and one by procedure, and `records/rn-accept-01/confirmation.yml` byte for byte the file on the node.
- Run it again: it must refuse, because the attempt is `confirmed`.
- `ansible-playbook destroy.yml -e hostname=rn-accept-01 -e raw_node_incus_project=uc-raw-node-test` must leave the attempt `destroyed` and the project empty.
- Record each step's timing, the network service RN-FW-04 found, and the Foomuuri version. If RN-FW-04 fails, stop and ask before changing Foomuuri's units.
- Tell me where the throwaway definition and passwords are, so I can log in at the console (RN-ACC-06) and use `sudo` with the password (RN-ACC-04) myself before marking the entry `active`.

### Documents and session record

- Update the README: status, the node definition's optional fields, the validator's key, and the build order.
- Commit `en/docs/guides/spinning-up-a-debian-13-incus-container-v0.1.0.md` as it is if it is not in the repository yet, then `git mv` it to v0.1.1 and update it: the real build now produces a raw node, the test wrapper becomes optional, the reference to the alignment document goes, and the guide adds the console and `sudo` checks.
- Do not write new versions of the design documents. I will write them from your session record.
- The session record goes in `en/docs/sessions/`, named `$(date +%Y-%m-%d--%H-%M-%S)-session.md` when you create it at the start. By the end it holds what each step did, every way you met a clause that the contract leaves open, anything the contract does not cover, the full check's result, the acceptance run with timings, and open questions for me.

### When to stop and ask

- A clause cannot be met on `images:debian/13` by the payload as described.
- RN-FW-04 fails as built.
- The contract is ambiguous on something the report or validator must decide.
- A check would need the initial or root password in clear.
- You would need to change anything outside `templates/`, `filter_plugins/`, `tasks/`, `roles/`, `registry/base.yml`, `vars/defaults.yml`, `tests/`, `tools/`, the entry playbooks, `README.md`, the guide and your session record.

## Changes

### From v0.1.0 to v0.2.0

- uc-raw-node now meets the contract on its own: no files from uc-ventoy, no vendored copy, no manifest. The node-side files, including the first-boot report, are uc-raw-node's own templates, built from the contract text.
- The payload is one self-contained script rendered from one template, so the transport's existing push and run deliver it unchanged, instead of a payload directory.
- Dropped the dependency on the alignment document. The decisions it held that still stand are written into this kickoff.
- Reduced the work to seven steps.

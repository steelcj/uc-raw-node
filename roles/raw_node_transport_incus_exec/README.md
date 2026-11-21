# raw_node_transport_incus_exec

Transport role for the uc-raw-node raw node controller. It delivers `raw-node-firstboot` to an Incus instance with `incus file push` and runs it once with `incus exec`. It is the transport for the `incus_container_default` registry entry (strategy `adopt`), which covers default Incus image variants that do not include cloud-init.

The role runs on the controller host, which must have the `incus` client configured for the target Incus server. It does not use SSH or inventory.

## Task files

| File | Called by | Does |
| :-- | :-- | :-- |
| `tasks/main.yml` | `build.yml` (`include_role`) | Launches or adopts the instance, delivers and runs the payload |
| `tasks/address.yml` | `main.yml`, and the controller's `wait_phone_home.yml` with `tasks_from: address` | Reports the instance's global addresses and SSH host public keys |
| `tasks/destroy.yml` | The controller's `handle_failure.yml` and `destroy.yml`, with `tasks_from: destroy` | Deletes the instance, if this controller created it |

## What main.yml does

- Checks its inputs and that the payload exists in the node's secrets directory (`<raw_node_secrets_dir>/<hostname>/raw-node-firstboot`).
- Looks up the instance. If it does not exist, launches it from `raw_node_incus_image` with the ownership marker (below). If it already exists, it refuses to continue unless `raw_node_incus_allow_existing` is true, so an unrelated container is never adopted by accident.
- Waits through `address.yml` until the instance is running with a global address, then waits for systemd to settle where systemd is present.
- Pushes the payload with mode 0700, owned by root, runs it once, and removes the staged copy inside the instance.
- Writes the payload's exit code and output to `<raw_node_logs_dir>/<hostname>/incus_exec-run.log`, mode 0600.
- Sets `raw_node_transport_result` (instance, project, whether this run created it, payload exit code, IPv4 and IPv6 global addresses, log path) and fails if the payload exited non-zero.

The push and the run carry `no_log: true`, since they handle the payload. When either fails, the next task sets `raw_node_failure_reason` from safe fields only (the step, the exit code and the log path, never the output) and fails with it, so the controller's failure record can say what happened. The run log keeps the payload's output, which the payload's own output rules keep free of contract values and the token.

## The ownership marker

When this transport launches an instance, it sets two Incus user keys at launch:

```text
user.uc-raw-node.created=true
user.uc-raw-node.hostname=<hostname>
```

`tasks/destroy.yml` deletes only an instance that carries both, with the hostname matching. Ownership is therefore recorded on the platform, not on the controller host, and teardown works from any controller host, including one without the node's records.

This is a rule every transport follows with whatever its platform offers: Incus user keys here, instance tags or labels on a cloud provider. A transport records ownership at creation time, atomically with the create call where the platform allows it, and checks it before every delete. A transport whose platform cannot carry a marker cannot destroy, and its registry entries set `can_destroy: false`.

The marker is backed by a second check in a build run: `destroy.yml` called from the rescue path only deletes an instance that this run launched, and never an instance that existed before and was adopted, even if it carries the marker. If this run launched nothing (for example, the payload step failed before the transport ran, or the transport refused an existing instance), teardown succeeds without touching any instance, so an earlier node with the same hostname is never deleted by a later failed attempt. The standalone `destroy.yml` sets `raw_node_destroy_standalone: true` and relies on the marker alone.

Teardown outcomes:

| Situation | Build run (rescue) | Standalone `destroy.yml` |
| :-- | :-- | :-- |
| No instance with that name | Nothing to delete, succeeds | Nothing to delete, succeeds |
| Instance launched by this run, marker present | Deleted | Not applicable |
| Instance carries the marker, launched earlier | Left alone, succeeds | Deleted |
| Instance adopted by this run | Refused, fails (controller quarantines) | Deleted only if it carries the marker |
| Instance without the marker | Left alone, succeeds | Refused, fails |

## Inputs

| Variable | Default | Meaning |
| :-- | :-- | :-- |
| `raw_node_platform` | Set by the controller | The resolved registry entry; its `transport` must be `incus_exec` |
| `raw_node_hostname` | Set by the controller | From the `hostname` field of the contract input; used as the instance name through `raw_node_incus_instance` |
| `raw_node_secrets_dir`, `raw_node_logs_dir` | Set by `prepare_paths.yml` | Expanded secrets and logs paths |
| `raw_node_incus_instance` | `{{ raw_node_hostname }}` | Instance name |
| `raw_node_incus_image` | `images:debian/13` | Image used when the instance does not exist |
| `raw_node_incus_project` | `default` | Incus project |
| `raw_node_incus_profiles` | `[default]` | Profiles applied at launch |
| `raw_node_incus_create` | `true` | Create the instance if it is missing |
| `raw_node_incus_wait_timeout` | `120` | Seconds `main.yml` waits for a running instance with a global address |
| `raw_node_incus_address_timeout` | `raw_node_report_timeout`, else `raw_node_incus_wait_timeout` | Seconds `address.yml` waits when called by the controller |
| `raw_node_payload_file` | `{{ raw_node_secrets_dir }}/{{ raw_node_hostname }}/raw-node-firstboot` | Payload rendered by `payload.yml` |
| `raw_node_incus_run_log` | `{{ raw_node_logs_dir }}/{{ raw_node_hostname }}/incus_exec-run.log` | Run log |
| `raw_node_incus_payload_dest` | `/root/raw-node-firstboot` | Absolute path for the payload inside the instance |
| `raw_node_incus_bin` | `incus` | Client binary, so tests can substitute a stand-in |
| `raw_node_destroy_standalone` | Unset (false) | Set by `destroy.yml`; teardown relies on the marker alone |

### Defaults and role vars

The controller loads its `vars/defaults.yml` through play `vars_files`, which outranks role defaults, so everything in `defaults/main.yml` is advisory and can be replaced by the play. Values the play must not override are in `vars/main.yml`, which outranks play vars, `vars_files` and inventory, and can only be replaced by `set_fact`, include parameters or `-e`:

- `raw_node_incus_allow_existing: false`. Adopting an instance that already exists is a deliberate decision for one run, made by the operator with `-e raw_node_incus_allow_existing=true`. Keeping it in role vars means a shared setting loaded by the play, such as a `vars_files` entry, cannot turn adoption on for every run by accident, while the operator's `-e` still works.
- The marker key names, `raw_node_incus_marker_created_key` and `raw_node_incus_marker_hostname_key`, which `main.yml` and `destroy.yml` must agree on.

The other settings stay in `defaults/main.yml` because an operator or the controller legitimately sets them: project, image, profiles, timeouts and the client binary.

## Outputs

| Variable | Set by | Meaning |
| :-- | :-- | :-- |
| `raw_node_transport_result` | `main.yml` | Instance, project, `created`, `payload_rc`, `ipv4`, `ipv6`, `log` |
| `raw_node_transport_address` | `address.yml` | `found`, `ipv4`, `ipv6`, `ssh_host_keys`, `waited` |
| `raw_node_failure_reason` | `main.yml`, on a failed push or payload run | Secret-free reason for the failure record |
| `raw_node_incus_launched`, `raw_node_incus_adopted` | `main.yml` | Whether this run launched or adopted the instance; read by `destroy.yml` |

## Testing

`tests/transport_incus_exec.yml` runs registry validation, loads `tests/fixtures/raw-node-input.yml`, resolves `incus_container_default`, prepares the output paths (all under `artifacts/`, through `tests/vars/output.yml`), stages the stand-in payload `tests/fixtures/raw-node-firstboot` in the node's secrets directory and delivers it. It checks the ownership marker, the run log and, with `raw_node_test_destroy=true`, that teardown removes the instance. A second case launches a plain instance without the marker and checks that the transport neither adopts it nor deletes it.

On an Incus host, from the repository root, in a dedicated project:

```sh
ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml \
  -e raw_node_incus_project=uc-raw-node-test -e raw_node_test_destroy=true
```

Without an Incus host, put the stand-in client in `tests/bin` first on the path. It keeps its state in `artifacts/fake-incus.json` (or `$FAKE_INCUS_STATE`), records `--config` keys, refuses to delete an instance without the marker, and runs pushed payloads locally:

```sh
PATH="$PWD/tests/bin:$PATH" ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml -e raw_node_test_destroy=true
```

The stand-in client checks the role's logic and command sequence only. A run on a real Incus host is still needed before `incus_container_default` can be marked `active`.

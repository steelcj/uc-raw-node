# raw_node_transport_incus_exec

Transport role for the uc-raw-node raw node controller. It delivers `raw-node-firstboot` to an Incus instance with `incus file push` and runs it once with `incus exec`. It is the transport for the `incus_container_default` registry entry (strategy `adopt`), which covers default Incus image variants that do not include cloud-init.

The role runs on the controller host, which must have the `incus` client configured for the target Incus server. It does not use SSH or inventory.

## What it does

- Checks its inputs and that the payload file exists on the controller.
- Looks up the instance. If it does not exist, launches it from `raw_node_incus_image`. If it already exists, it refuses to continue unless `raw_node_incus_allow_existing` is true, so an unrelated container is never adopted by accident.
- Waits until the instance is running and has a global address, then waits for systemd to settle where systemd is present.
- Pushes the payload with mode 0700, owned by root, runs it once, and removes the staged copy.
- Saves the payload's exit code and output to `incus_exec-run.log` in `raw_node_artifacts_dir`.
- Sets `raw_node_transport_result` (instance, project, whether this run created it, payload exit code, IPv4 and IPv6 global addresses) and fails if the payload exited non-zero.

`tasks/destroy.yml` is called by the controller's `failure.yml` when the platform's `can_destroy` is true. It only deletes an instance that this run created; an adopted instance is left in place with a message.

## Inputs

| Variable | Default | Meaning |
| :-- | :-- | :-- |
| `raw_node_platform` | Set by the controller | The resolved registry entry; its `transport` must be `incus_exec` |
| `raw_node_hostname` | Set by the controller | From the `hostname` field of `raw-node-input.yml`; used as the instance name through `raw_node_incus_instance` |
| `raw_node_artifacts_dir` | Set by the controller | Where the payload is read from and the run log is written |
| `raw_node_incus_image` | `images:debian/13` | Image used when the instance does not exist |
| `raw_node_incus_project` | `default` | Incus project |
| `raw_node_incus_profiles` | `[default]` | Profiles applied at launch |
| `raw_node_incus_create` | `true` | Create the instance if it is missing |
| `raw_node_incus_allow_existing` | `false` | Allow adopting an instance that already exists |
| `raw_node_incus_wait_timeout` | `120` | Seconds to wait for a running instance with a global address |
| `raw_node_payload_file` | `{{ raw_node_artifacts_dir }}/raw-node-firstboot` | Payload rendered by `payload.yml` |
| `raw_node_incus_payload_dest` | `/root/raw-node-firstboot` | Absolute path for the payload inside the instance |
| `raw_node_incus_bin` | `incus` | Client binary, so tests can substitute a stand-in |

## Testing

`tests/transport_incus_exec.yml` runs registry validation, loads `tests/fixtures/raw-node-input.yml`, resolves `incus_container_default`, and delivers the stand-in payload in `tests/fixtures/raw-node-firstboot`.

On an Incus host, from the repository root:

```sh
ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml
ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml -e raw_node_test_destroy=true
```

Without an Incus host, put the stand-in client in `tests/bin` first on the path. It records state in `/tmp/fake-incus.json` (or `$FAKE_INCUS_STATE`) and runs pushed payloads locally:

```sh
PATH="$PWD/tests/bin:$PATH" ansible-playbook -i localhost, -c local tests/transport_incus_exec.yml
```

The stand-in client checks the role's logic and command sequence only. A run on a real Incus host is still needed before `incus_container_default` can be marked `active`.

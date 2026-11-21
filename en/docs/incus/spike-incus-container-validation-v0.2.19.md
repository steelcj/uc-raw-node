---
title: "Spike: Incus Container Validation"
version: "0.2.18"
date: 2026-11-20
author: "Christopher Steel"
status: "First container run complete on 2026-11-20, ready for a clean confirming run"
description: "A time-boxed test of whether unprivileged Incus containers can meet the clauses of raw node contract 0.3.0, and which clauses need a contract review before the Incus backend of uc-raw-node supports containers."
---

# Spike: Incus Container Validation

## Purpose

This spike determines, by testing rather than by reading, whether an unprivileged Incus container can be a raw node under contract 0.3.0, as uc-ventoy baseline 0.4.0 implements it. It answers the open points in the Incus notes of `backend-contract.md`: whether the Foomuuri firewall loads and is enforced, whether the MAC-derived hostname suffix is stable, whether the first-boot report works, and which clauses assume something a container does not own.

The outcome is a decision on whether the Incus backend supports containers, virtual machines or both, recorded in the coverage table of the Incus backend document.

Allow 20 to 30 minutes if everything works, longer if the firewall needs investigation.

## Prerequisites

| Item | Requirement |
| --- | --- |
| Host | Debian 13 or Ubuntu 24.04 or later |
| Incus | 6.x or later, checked with `incus version` |
| Network | The `incusbr0` bridge exists with DHCP enabled, and the `default` profile attaches `eth0` to it |
| Image | `images:debian/13/cloud`, fetched automatically on first launch |
| Node files | `uc-ventoy-spike-files.tar.gz`, rendered from uc-ventoy commit `5ed7bb8` (baseline 0.4.0, contract 0.3.0) with `ssh_port` 22, empty `ssh_sources` and the user `initial`. Its `optional/` folder holds the Foomuuri drop-in for both `foomuuri.service` and `foomuuri-boot.service`. |
| Tools | `mkpasswd` (package `whois`), `nc`, `curl` and `nmap` on the host |

Confirm that the image exists on the remote:

```sh
incus image info images:debian/13/cloud
```

Output example:

```bash
Fingerprint: f0b9237ae65ed183d4ee5c672dbadcded89226159fe779951e89cfac8a00d8d6
Size: 132.40MiB
Architecture: x86_64
Type: container
Public: yes
Timestamps:
    Created: 2026/11/17 19:00 EST
    Uploaded: 2026/11/17 19:00 EST
    Expires: 1969/12/31 19:00 EST
    Last used: never
Properties:
    architecture: amd64
    description: Debian trixie amd64 (cloud) (20261118_05:24)
    os: Debian
    release: trixie
    serial: 20261118_05:24
    type: squashfs
    variant: cloud
Aliases:
    - debian/trixie/cloud
    - debian/trixie/cloud/amd64
    - debian/13/cloud
    - debian/13/cloud/amd64
Cached: no
Auto update: disabled
Profiles: []
```

Check whether the bridge hands out IPv6 addresses:

```sh
incus network get incusbr0 ipv6.address
```

Output example:

```bash
fd42:48:ed9e:b152::1/64
```

If this prints an address, containers get IPv6 through SLAAC or DHCPv6 and the interface's `ip6` list in the report should have a value. If it prints nothing or `none`, the list will be empty. Both are valid raw nodes, because the report records what is measured, as on a network without IPv6. Record which case the spike ran under, since a real deployment may expect IPv6 where the spike had none.

The commands below always pass `--project spike-incus`, so nothing lands in the default project even if you forget to switch.

## Create a test project

For a clean run, start with no `spike-incus` project. If one is left from an earlier run, remove it and its instances first, as in [Clean up](#clean-up).

Create a project that isolates the spike's instances but shares images and profiles with the default project:

```sh
incus project create spike-incus \
  --config features.images=false \
  --config features.profiles=false
```

Output example:

```bash
Project spike-incus created
```

Both options are needed. A project created without options isolates images and profiles <a id="cite-incus-projects"></a>([Linux Containers, n.d.-c](#ref-incus-projects)). With isolated profiles, the project gets its own empty `default` profile, which has no root disk and so cannot create instances <a id="cite-incus-projects-create"></a>([Linux Containers, n.d.-a](#ref-incus-projects-create)). It would also have no `eth0`. Setting both features to `false` lets the spike use the default project's images and its `default` profile, root disk and network included, with no profile setup.

## Prepare the user data

The user data creates the initial user and sets the root password, which is what the four values in `raw-node-input.yml` describe. Use the values from your own `raw-node-input.yml`, where `initial_password_hash` is the batch password hash, or generate test values. It also installs the SSH server, Foomuuri, the firewall manager uc-ventoy uses, and `sudo`.

### Template

This creates `spike-user-data.yml`. `mkpasswd` asks for each password in turn.

```sh
ROOT_HASH=$(mkpasswd --method=sha-512)
USER_HASH=$(mkpasswd --method=sha-512)
SSH_KEY=$(cat ~/.ssh/id_ed25519.pub)

cat > spike-user-data.yml <<EOF
#cloud-config
users:
  - name: initial
    groups: sudo
    shell: /bin/bash
    lock_passwd: false
    hashed_passwd: "${USER_HASH}"
    ssh_authorized_keys:
      - "${SSH_KEY}"
chpasswd:
  expire: false
  users:
    - name: root
      password: "${ROOT_HASH}"
      type: hash
packages:
  - openssh-server
  - foomuuri
  - sudo
EOF
```

Real world example, with a test passphrase only. `mkpasswd` asks for the passphrase and prints its hash:

```bash
mkpasswd --method=sha-512
$6$xreLdXj7wyetgd2V$fLe4bRSOXxBnQoBLpF2dZDAnnJjMx6FC7lle4n88FOpnAw/M0Rhlf0/vO2zaexf5wlWSF.QpEN2s24AwwlZpj/
```

Assign the hash in single quotes, as [With existing hashes](#with-existing-hashes) explains:

```bash
ROOT_HASH='$6$7hrSuIDK.fk2UhzH$mrDMuuWcPMvm3.SiCWMpNyl87Xihk19aDZraYmp2yUcEUoqUfiQjVVA3OmVV8eKtg18WQtTxRZWSRTKf2Awa7.'
USER_HASH='$6$7hrSuIDK.fk2UhzH$mrDMuuWcPMvm3.SiCWMpNyl87Xihk19aDZraYmp2yUcEUoqUfiQjVVA3OmVV8eKtg18WQtTxRZWSRTKf2Awa7.'
SSH_KEY=$(cat ~/.ssh/gradus-raw-initial-id_ed25519.pub)

cat > spike-user-data.yml <<EOF
#cloud-config
users:
  - name: initial
    groups: sudo
    shell: /bin/bash
    lock_passwd: false
    hashed_passwd: "${USER_HASH}"
    ssh_authorized_keys:
      - "${SSH_KEY}"
chpasswd:
  expire: false
  users:
    - name: root
      password: "${ROOT_HASH}"
      type: hash
packages:
  - openssh-server
  - foomuuri
  - sudo
EOF
grep -c '\$6\$' spike-user-data.yml
```

The `grep` should print `2`. If it prints `0`, the hashes were assigned without quotes and the passwords will not work at the console or for `sudo`.

`openssh-server` has to be listed. The `images:debian/13/cloud` image does not include it, although cloud-init still generates SSH host keys, so `/etc/ssh` looks complete without it. With no `sshd`, `raw-node-report` cannot read the SSH settings and writes no report. The Debian installer and Ubuntu bring the package themselves, so the Ventoy targets never needed it in the list.

### With existing hashes

To reuse hashes you already have, assign them in single quotes. A crypt hash is full of `$` signs, and without single quotes the shell expands `$6`, `$5Jpj…` and the rest as variables, which silently corrupts the hash. Keep real hashes out of published copies of this document.

```bash
ROOT_HASH='$6$<salt>$<root-hash>'
USER_HASH='$6$<salt>$<initial-batch-hash>'
SSH_KEY=$(cat ~/.ssh/gradus-raw-initial-id_ed25519.pub)
```

Then run the same `cat > spike-user-data.yml <<EOF` block as in the template. Inside the unquoted heredoc the shell substitutes each variable once and does not expand the `$` signs in its value, so the hashes arrive intact. Check with `grep -c '\$6\$' spike-user-data.yml`, which should print `2`.

Each user's keys go under that user's `ssh_authorized_keys`, and `lock_passwd: false` is needed for the password to work at all <a id="cite-cloudinit-users"></a>([cloud-init, n.d.-b](#ref-cloudinit-users)). Under contract 0.3.0 that password is for the console (RN-ACC-06) and for `sudo` (RN-ACC-04). SSH refuses passwords (RN-SSH-03). Root already exists, so its password is set through `chpasswd` rather than `users`, using `type: hash` for a crypt hash <a id="cite-cloudinit-setpasswords"></a>([cloud-init, n.d.-a](#ref-cloudinit-setpasswords)).

The user data does not set `ssh_pwauth`. SSH authentication is decided by the canonical drop-in installed later, which is one of the things this spike checks.

## Launch the container with a fixed MAC address

Choose a locally administered MAC address so that the hostname suffix is known in advance, and build the instance name from it with the hostname rule `<prefix>-<backend>-<mac4>`:

```sh
TEST_MAC="02:aa:bb:cc:dd:01"
MAC4=$(printf '%s' "${TEST_MAC//:/}" | tail -c 4)
I="deb13-ic-${MAC4}"
echo "Instance and hostname: ${I}"
```

Output example:

```bash
Instance and hostname: deb13-ic-dd01
```

Delete any instance left over from an earlier run in the `spike-incus` project:

```bash
incus delete deb13-ic-dd01 --project spike-incus --force
```

This gives `deb13-ic-dd01`. Launch it:

```sh
incus launch images:debian/13/cloud "${I}" \
  --project spike-incus \
  --device eth0,hwaddr="${TEST_MAC}" \
  --config cloud-init.user-data="$(cat spike-user-data.yml)"
```

Output:

```bash
Launching deb13-ic-dd01
```

`hwaddr` is the NIC option that sets the interface's MAC address, and it is assigned randomly when unset <a id="cite-incus-nic"></a>([Linux Containers, n.d.-d](#ref-incus-nic)). Because `eth0` comes from the `default` profile, `--device` overrides that profile device for this instance only. The flag takes one property per use <a id="cite-incus-device-flag"></a>([Incus init, n.d.](#ref-incus-device-flag)). The override merges rather than replaces: Incus copies the profile's `eth0`, including `network=incusbr0`, into the instance and changes only `hwaddr`. Passing `hwaddr` alone is therefore enough. Incus reads user data from the `cloud-init.user-data` option, and images from the `images:` remote with the `/cloud` suffix include cloud-init <a id="cite-incus-cloudinit"></a>([Linux Containers, n.d.-b](#ref-incus-cloudinit)).

## Wait for cloud-init

```bash
incus list "${I}" --project spike-incus
```

Output example:

```bash
┌───────────────┬─────────┬───────────────────────┬────────────────────────────────────────────┬───────────┬───────────┐
│     NAME      │  STATE  │         IPV4          │                    IPV6                    │   TYPE    │ SNAPSHOTS │
├───────────────┼─────────┼───────────────────────┼────────────────────────────────────────────┼───────────┼───────────┤
│ deb13-ic-dd01 │ RUNNING │ 10.119.134.150 (eth0) │ fd42:48:ed9e:b152:aa:bbff:fecc:dd01 (eth0) │ CONTAINER │ 0         │
└───────────────┴─────────┴───────────────────────┴────────────────────────────────────────────┴───────────┴───────────┘
```

```sh
incus exec "${I}" --project spike-incus -- cloud-init status --wait
```

Output example:

```bash
status: done
```

The status should end with `status: done`. If it reports an error, read the log:

```sh
incus exec "${I}" --project spike-incus -- cat /var/log/cloud-init-output.log
```

### Adhoc installations

If you are testing and some application is missing you can install it with something like this on a debian based container.:

```sh
incus exec "${I}" --project spike-incus -- sh -c 'apt-get update && apt-get install -y openssh-server foomuuri sudo'
```

## Install the canonical files and run first boot

The real Incus backend will deliver these files through cloud-init. The spike pushes them directly, so that a failure points at the container rather than at the delivery method.

`uc-ventoy-spike-files.tar.gz` holds the files a uc-ventoy node receives, rendered by `bin/build`'s own code, so they are byte for byte what the Debian 13 answer file writes. The one difference is `RAW_NODE_TARGET=incus/debian/13` in `raw-node.conf`, which the scripts record but do not act on. `MANIFEST` lists each file's mode and path on the node. If your `raw-node-input.yml` sets `ssh_port` or `ssh_sources`, the Foomuuri file and the port drop-in must be rendered again from it.

Extract the archive and push every file in the manifest:

```sh
tar -xzf uc-ventoy-spike-files.tar.gz
cat spike-files/MANIFEST

grep -v '^#' spike-files/MANIFEST | while read -r mode path; do
  incus file push "spike-files/rootfs${path}" "${I}${path}" --project spike-incus \
    --uid 0 --gid 0 --mode "${mode}" --create-dirs
done
```

Then push the Foomuuri drop-in for both `foomuuri.service` and `foomuuri-boot.service`. They must be in place before Foomuuri is enabled, because on this cloud image Foomuuri's default boot ordering forms a cycle with cloud-init, see [Boot does not finish: the hidden ordering cycle](#boot-does-not-finish-the-hidden-ordering-cycle):

```sh
for u in foomuuri foomuuri-boot; do
  incus file push "spike-files/optional/etc/systemd/system/${u}.service.d/10-raw-node.conf" \
    "${I}/etc/systemd/system/${u}.service.d/10-raw-node.conf" --project spike-incus \
    --uid 0 --gid 0 --mode 0644 --create-dirs
done
```

Then do what the Debian 13 answer file does at the end of the install. `nftables.service` is masked because stopping it flushes the whole ruleset, and only `foomuuri.service` is enabled because it starts `foomuuri-boot.service` by itself:

```bash
incus exec "${I}" --project spike-incus -- sh -c '
  systemctl daemon-reload
  systemctl mask nftables.service
  systemctl enable foomuuri.service raw-node-firstboot.service
'
```

Output:

```bash
  systemctl daemon-reload
  systemctl mask nftables.service
  systemctl enable foomuuri.service raw-node-firstboot.service
'
Created symlink '/etc/systemd/system/nftables.service' → '/dev/null'.
Created symlink '/etc/systemd/system/multi-user.target.wants/foomuuri.service' → '/usr/lib/systemd/system/foomuuri.service'.
Created symlink '/etc/systemd/system/multi-user.target.wants/raw-node-firstboot.service' → '/etc/systemd/system/raw-node-firstboot.service'.
```

then:

```bash
incus restart "${I}" --project spike-incus
for n in $(seq 1 40); do
  state=$(incus exec "${I}" --project spike-incus -- systemctl show -p ActiveState --value raw-node-firstboot 2>/dev/null)
  case "${state}" in active|failed) break ;; esac
  sleep 3
done
echo "raw-node-firstboot: ${state:-unknown}"
incus exec "${I}" --project spike-incus -- cat /var/lib/raw-node/confirmation.yml
```

Output example:

```bash
raw-node-firstboot: active
deb13-ic-dd01:
  contract: 0.3.0
  baseline: 0.4.0
  timestamp: 2026-11-21T01:27:32+00:00
  machine_id: "a5ba0ec47ad341e98f6d7fecf523af14"
  user: initial
  sudo: true
  sudo_nopasswd: false
  ssh_port: 22
  ssh_password_auth: false
  ssh_host_keys:
    - type: ecdsa-sha2-nistp256
      fingerprint: "SHA256:aiSZhtIWZ1kSJGTBRrTUV+fF/agK//1Y8M0pciCp/8o"
    - type: ssh-ed25519
      fingerprint: "SHA256:icKO9dvaEgSQnxaNhMRSwNErEdRBOFUeNUitQDnq0AU"
    - type: ssh-rsa
      fingerprint: "SHA256:r+b4+6DStEGo8wlT7xA/aiDDnf31XciXU+QmghcX3Es"
  firewall: foomuuri
  firewall_active: true
  python: /usr/bin/python3
  interfaces:
    - name: eth0
      type: other
      mac: "02:aa:bb:cc:dd:01"
      state: up
      default_route4: true
      default_route6: false
      ip: [10.119.134.150]
      ip6: []
```

`raw-node-firstboot` waits up to 60 seconds for a default route before it measures anything, so the loop waits until the unit has finished rather than for a fixed time. Just after the restart, systemd in the container is not up yet and `systemctl` prints `Failed to connect to system scope bus`, which the loop hides and waits through. `active` means the unit succeeded and `failed` means it did not. `unknown` or `inactive` after the loop means it never ran: see the condition check below.

The report should have the contract 0.3.0 fields, with values measured on the node, as in the output example above. Points to record from that run:

| Field | Observed | Note |
| --- | --- | --- |
| `ssh_host_keys` | Three keys: ECDSA, Ed25519 and RSA, generated by cloud-init | Key types are written as OpenSSH names them, such as `ssh-ed25519` |
| `interfaces[].type` | `other` | A container's `eth0` is one end of a virtual pair, not an Ethernet device. The contract does not require a type. |
| `timestamp` | `+00:00` | The container's time zone is UTC |
| `default_route6`, `ip6` | `false`, empty | `incus list` showed a global IPv6 address on `eth0` before the firewall was installed. See [Check IPv6 after first boot](#check-ipv6-after-first-boot). |
| Hostname | `deb13-ic-dd01` | Unchanged, as expected for a name not ending in `-vt` |

### Check IPv6 after first boot

If the bridge provides IPv6 but the report has none, find out whether the report measured too early or the firewall blocks router advertisements:

```bash
incus exec "${I}" --project spike-incus -- sh -c '
  ip -6 addr show dev eth0 scope global
  ip -6 route show default
  nft list table inet foomuuri | grep -i -E "icmpv6|nd-router|router-advert" | head
'
```

Output:

```bash
7: eth0@if8: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000 link-netnsid 0
    inet6 fd42:48:ed9e:b152:aa:bbff:fecc:dd01/64 scope global mngtmpaddr noprefixroute 
       valid_lft forever preferred_lft forever
default nhid 3703297815 via fe80::1266:6aff:fe6f:987a dev eth0 proto ra metric 1024 expires 1574sec pref medium
		icmpv6 type { destination-unreachable, packet-too-big, time-exceeded, parameter-problem, nd-router-solicit, nd-neighbor-solicit, nd-neighbor-advert, ind-neighbor-solicit, ind-neighbor-advert } accept
		icmpv6 type . ip6 saddr { nd-router-advert . fe80::/10, mld-listener-query . fe80::/10, mld-listener-report . fe80::/10, mld-listener-done . fe80::/10, 149 . fe80::/10, 151 . fe80::/10, 152 . fe80::/10, 153 . fe80::/10, mld2-listener-report . fe80::/10, mld2-listener-report . ::, 148 . fe80::/10, 148 . :: } accept
		ip6 saddr :: icmpv6 type mld2-listener-report accept
		icmpv6 type echo-request accept
```

```sh
incus list "${I}" --project spike-incus -c 6
```

Output

```bash
┌────────────────────────────────────────────┐
│                    IPV6                    │
├────────────────────────────────────────────┤
│ fd42:48:ed9e:b152:aa:bbff:fecc:dd01 (eth0) │
└────────────────────────────────────────────┘
```

| Observation | Meaning |
| --- | --- |
| A global address and a default route are there now | Timing: `raw-node-firstboot` measures as soon as an IPv4 or IPv6 default route exists, before SLAAC completes. The report is right for the moment it ran. Record whether the Incus backend should wait for both. |
| Still no address or route | The firewall drops router advertisements, which RN-FW-03 requires to be accepted as ICMPv6 that networking needs. Record it against RN-FW-03. |

Result of the run: timing. The address and a default route learned from a router advertisement (`proto ra`) were there after first boot, and the Foomuuri table accepts `nd-router-advert` from `fe80::/10`. The firewall is not at fault. The report measured before SLAAC completed, so its `ip6` list is empty.

### If the report is missing

If the report is missing after the restart, check how the unit decides to run before blaming the container:

```sh
incus exec "${I}" --project spike-incus -- systemctl cat raw-node-firstboot | grep -i condition
```

The uc-ventoy unit has `ConditionPathExists=!/var/lib/raw-node/confirmation.yml`, so a restart re-triggers it as long as no report exists yet. Run the unit by hand to test the script in isolation, and treat the trigger as a separate finding:

```sh
incus exec "${I}" --project spike-incus -- systemctl restart raw-node-firstboot
incus exec "${I}" --project spike-incus -- systemctl status raw-node-firstboot --no-pager -l
incus exec "${I}" --project spike-incus -- journalctl -b -u raw-node-firstboot --no-pager -l
```

Output:

```bash
○ raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report
     Loaded: loaded (/etc/systemd/system/raw-node-firstboot.service; enabled; preset: enabled)
    Drop-In: /run/systemd/system/service.d
             └─zzz-lxc-service.conf
     Active: inactive (dead) since Sat 2026-11-21 01:34:01 UTC; 36ms ago
   Duration: 6min 28.120s
 Invocation: c4e3a6b9299d4673a8cf537aaba6ca07
  Condition: start condition unmet at Sat 2026-11-21 01:34:01 UTC; 36ms ago
             └─ ConditionPathExists=!/var/lib/raw-node/confirmation.yml was not met
       Docs: file:/usr/local/sbin/raw-node-firstboot
    Process: 214 ExecStart=/usr/local/sbin/raw-node-firstboot (code=exited, status=0/SUCCESS)
   Main PID: 214 (code=exited, status=0/SUCCESS)

Nov 21 01:27:32 deb13-ic-dd01 systemd[1]: Starting raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report...
Nov 21 01:27:33 deb13-ic-dd01 systemd[1]: Finished raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report.
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: raw-node-firstboot.service: Deactivated successfully.
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: Stopped raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report.
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: Stopping raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report...
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report skipped, unmet condition check ConditionPathExists=!/var/lib/raw-node/confirmation.yml
Nov 21 01:27:32 deb13-ic-dd01 systemd[1]: Starting raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report...
Nov 21 01:27:33 deb13-ic-dd01 systemd[1]: Finished raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report.
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: raw-node-firstboot.service: Deactivated successfully.
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: Stopped raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report.
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: Stopping raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report...
Nov 21 01:34:01 deb13-ic-dd01 systemd[1]: raw-node-firstboot.service - Raw node first boot: hostname suffix and confirmation report skipped, unmet condition check ConditionPathExists=!/var/lib/raw-node/confirmation.yml
```

Use `restart` rather than `start`. A `Type=oneshot` unit with `RemainAfterExit=yes` that already exited cleanly stays active, and `start` then does nothing. If the condition is not met, neither command runs the script, and `status` names the condition that skipped it. When the report cannot measure the node, the unit fails with status 2 and writes no `confirmation.yml`, so it runs again at the next boot. The journal names each value that could not be measured, and so does `/etc/issue.d/50-raw-node.issue`. The script deletes its own `report.err` when it finishes, so do not look for that file.

| Journal line | Cause | Fix |
| --- | --- | --- |
| `cannot read passwordauthentication and kbdinteractiveauthentication from sshd -G or sshd -T` | No `sshd`: `openssh-server` is not installed | Install it, then restart the unit |
| No SSH host key | Host keys not generated yet | Run `ssh-keygen -A`, then restart the unit |

Note the hostname the report shows. `raw-node-firstboot` appends the MAC suffix only to a hostname ending in `-vt`, the Ventoy installer's name. `deb13-ic-dd01` already carries its suffix and is left as it is. Record it as a finding: the Incus backend either keeps naming instances with the suffix at launch, or `raw-node-firstboot` learns the `-ic` ending.

## Test the firewall

This is the critical gate. Foomuuri has to load its ruleset inside the unprivileged container and actually filter traffic, as RN-FW-01 to RN-FW-04 require.

Check that Foomuuri is running and owns the only table, as RN-FW-01 and RN-FW-02 require:

```sh
incus exec "${I}" --project spike-incus -- sh -c '
  systemctl is-enabled nftables.service foomuuri.service
  systemctl is-active foomuuri.service
  nft list tables
  ls -la /etc/foomuuri
  nft list table inet foomuuri | grep -q "dport 22" || echo "SSH RULE MISSING"
'
```

Output:

```bash
masked
enabled
active
table inet foomuuri
total 4
drwxr-xr-x 1 root root   32 Nov 20 22:40 .
drwxr-xr-x 1 root root 2144 Nov 20 22:42 ..
-rw-r--r-- 1 root root  901 Nov 20 22:40 00-raw-node.conf
```

Expected: `masked` and `enabled`, then `active`, then only `table inet foomuuri`, and only `00-raw-node.conf` in `/etc/foomuuri`. The last check matters because an active service does not prove the raw node rules are loaded.

Then check that the rules are enforced, as RN-FW-03 requires. Start a listener on a port the raw node firewall does not open, confirm it answers from inside, and confirm it is blocked from the host while SSH is not:

```sh
IP=$(incus list "${I}" --project spike-incus -c 4 -f csv | cut -d' ' -f1)

incus exec "${I}" --project spike-incus -- \
  systemd-run --unit=spike-http python3 -m http.server 8080
sleep 1
incus exec "${I}" --project spike-incus -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080').status)"

nc -zv -w 3 "${IP}" 22
curl --max-time 3 "http://${IP}:8080/" || echo "BLOCKED, as expected"
ping -c 2 "${IP}"
nmap -Pn -p 1-1024 "${IP}"
```

Output:

```bash
Running as unit: spike-http.service; invocation ID: 4caf58a0b192482884a92b8a48366800
200
Connection to 10.119.134.150 22 port [tcp/ssh] succeeded!
curl: (28) Connection timed out after 3001 milliseconds
BLOCKED, as expected
PING 10.119.134.150 (10.119.134.150) 56(84) bytes of data.
64 bytes from 10.119.134.150: icmp_seq=1 ttl=64 time=0.046 ms
64 bytes from 10.119.134.150: icmp_seq=2 ttl=64 time=0.048 ms

--- 10.119.134.150 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss, time 1051ms
rtt min/avg/max/mdev = 0.046/0.047/0.048/0.001 ms
Starting Nmap 7.94SVN ( https://nmap.org ) at 2026-11-20 20:35 EST
Nmap scan report for deb13-ic-dd01.incus (10.119.134.150)
Host is up (0.000099s latency).
Not shown: 1023 filtered tcp ports (no-response)
PORT   STATE SERVICE
22/tcp open  ssh

Nmap done: 1 IP address (1 host up) scanned in 6.53 seconds
```

The listener answers `200` from inside the container, and the host's `curl` times out on the same port, so the firewall drops it: RN-FW-03 is enforced. `nmap` reports 1023 ports `filtered` and only 22 `open`, ping answers, and SSH connects. Stop the listener afterwards with `incus exec "${I}" --project spike-incus -- systemctl stop spike-http`.

The listener runs under `systemd-run` because a process started with `nohup … &` inside `incus exec` ends when the exec session ends. An earlier run that used `nohup` got `Connection refused` from inside.

Finally, check RN-FW-04, that the firewall is in force before the network comes up. On Ubuntu, cloud-init and Foomuuri form an ordering cycle that systemd breaks by not starting one of them, and the Debian cloud image also boots with cloud-init:

Note: this takes a few seconds with both drop-ins in place, and up to 120 seconds if the ordering cycle is present:

```sh
incus restart "${I}" --project spike-incus
sleep 3
incus exec "${I}" --project spike-incus -- sh -c '
  timeout 120 systemctl is-system-running --wait
  systemctl list-jobs --no-pager
  journalctl -b | grep -i -E "ordering cycle|deleted to break"
  systemctl show --property=Id,ActiveEnterTimestampMonotonic \
    foomuuri-boot.service foomuuri.service network-pre.target \
    systemd-networkd.service networking.service
'
```

Output example:

```bash
running
No jobs running.
Id=foomuuri-boot.service
ActiveEnterTimestampMonotonic=1459825709

Id=foomuuri.service
ActiveEnterTimestampMonotonic=1459995482

Id=network-pre.target
ActiveEnterTimestampMonotonic=1459997109

Id=systemd-networkd.service
ActiveEnterTimestampMonotonic=1460034369

Id=networking.service
ActiveEnterTimestampMonotonic=0
```

The order in the output example above:

| Unit Order                 | Active at (µs, host clock) | After the previous unit |
| -------------------------- | -------------------------- | ----------------------- |
| `foomuuri-boot.service`    | 155379987925               |                         |
| `foomuuri.service`         | 155380176907               | 0.19 s                  |
| `network-pre.target`       | 155380177213               | 0.3 ms                  |
| `systemd-networkd.service` | 155380224408               | 47 ms                   |

The times are microseconds on the host's monotonic clock, which containers share, which is why they are so large. Foomuuri loaded its rules before `network-pre.target`, and the network came up after that through `systemd-networkd`. The image does not use `networking.service`, so it shows `0`.

The cycle check printed nothing, but `list-jobs` shows `cloud-config.service` stuck and boot never finishing. That is an ordering cycle the journal did not show, see [Boot does not finish: the hidden ordering cycle](#boot-does-not-finish-the-hidden-ordering-cycle). The firewall order was right in this run, but only because systemd chose to drop a cloud-init job rather than a Foomuuri one.

RN-FW-04 is met when `foomuuri.service` became active before `network-pre.target`, and `network-pre.target` before whichever network service the image uses. A unit that is not installed shows `0`. The order is read from each unit's activation time rather than from `systemd-analyze critical-chain`, because `critical-chain` only answers once boot has finished, and in this container boot may not finish: `systemctl is-system-running --wait` waited without end in one run. `timeout 120` bounds that wait, and `list-jobs` shows any job holding boot open.

Output from an earlier version of this step, which waited 5 seconds and used `critical-chain`:

```bash
Bootup is not yet finished (org.freedesktop.systemd1.Manager.FinishTimestampMonotonic=0).
Please try again later.
Hint: Use 'systemctl list-jobs' to see active jobs
Nov 20 23:13:39 deb13-ic-dd01 systemd[1]: Starting foomuuri-boot.service - Multizone bidirectional nftables firewall - Early boot...
Nov 20 23:13:39 deb13-ic-dd01 systemd[1]: Finished foomuuri-boot.service - Multizone bidirectional nftables firewall - Early boot.
Nov 20 23:13:39 deb13-ic-dd01 systemd[1]: Starting foomuuri.service - Multizone bidirectional nftables firewall...
Nov 20 23:13:39 deb13-ic-dd01 foomuuri[206]: start success
Nov 20 23:13:39 deb13-ic-dd01 systemd[1]: Finished foomuuri.service - Multizone bidirectional nftables firewall.
```

In that run the journal shows no ordering cycle, and both Foomuuri units started cleanly, but `critical-chain` refused to answer because boot had not finished. Run the step above to complete RN-FW-04.

### Boot does not finish: the hidden ordering cycle

After Foomuuri was enabled, every boot of the container left `cloud-config.service` running and `cloud-final.service` and `cloud-init.target` waiting, so `systemctl is-system-running` stayed at `starting`. To see what it waits on:

```sh
incus exec "${I}" --project spike-incus -- sh -c '
  systemctl status cloud-config.service --no-pager -l | head -20
  ps -eo pid,etime,args --forest | grep -B1 -A6 "[c]loud-init"
  tail -n 30 /var/log/cloud-init.log
'
```

In the run, `cloud-config.service` had been in `activating (start)` for 10 minutes, its process was `echo "start" | nc -Uu … /run/cloud-init/share/config.sock`, and `cloud-init --all-stages` was still running. The last line of `cloud-init.log` was:

```text
socket.py[INFO]: Sending sd_notify(STATUS=Waiting on external services to complete before starting the network stage.)
```

This cloud-init runs every stage in one process, `cloud-init --all-stages`, and each stage's systemd service releases its stage by sending `start` over a socket. The network stage is released by `cloud-init-network.service`, which was neither running nor waiting in `list-jobs`, so `cloud-config` waits behind a stage that never starts. A job that vanishes like this is how systemd breaks an ordering cycle. The cycle is the one the uc-ventoy Ubuntu targets fix with a drop-in: `foomuuri.service` is ordered before `network-pre.target` and, through its default dependencies, after `sysinit.target`, while cloud-init's network stage is ordered before `sysinit.target`. First boot finished because Foomuuri was not yet enabled. The `journalctl` check found nothing because in a container systemd's earliest boot messages do not reach the journal.

Confirm the cycle:

```sh
incus exec "${I}" --project spike-incus -- sh -c '
  systemctl status cloud-init-network.service --no-pager | head -4
  systemd-analyze verify default.target 2>&1 | grep -i -E "cycle|deleted"
'
```

Output example:

```bash
● cloud-init-network.service - Cloud-init: Network Stage
     Loaded: loaded (/usr/lib/systemd/system/cloud-init-network.service; enabled; preset: enabled)
    Drop-In: /run/systemd/system/service.d
             └─zzz-lxc-service.conf
```



The unit files confirm the loop. `cloud-init-network.service` is ordered before `sysinit.target` and after `systemd-networkd-wait-online.service`:

```bash
Before=sysinit.target raw-node-firstboot.service chronyd.service sshd-keygen.service ssh.service cloud-config.target systemd-user-sessions.service network-online.target shutdown.target
After=systemd-journald.socket system.slice networking.service systemd-networkd-wait-online.service cloud-init-local.service
```

With default dependencies, a Foomuuri unit starts after `sysinit.target`, and `systemd-networkd` waits for Foomuuri through `network-pre.target`, so the loop is: `sysinit.target`, Foomuuri, `network-pre.target`, `systemd-networkd`, `systemd-networkd-wait-online`, cloud-init's network stage, and back to before `sysinit.target`.

Systemd does not promise which job it drops to break a cycle. Without any drop-in it dropped cloud-init's network stage. The fix is the drop-in the uc-ventoy Ubuntu targets use, which removes Foomuuri's default dependencies, and on Debian 13 it is needed on both Foomuuri units. Foomuuri 0.27 splits the firewall into `foomuuri-boot.service` and `foomuuri.service`, and `foomuuri.service` is ordered after `foomuuri-boot.service`. With the drop-in on `foomuuri.service` alone, the loop ran through `foomuuri-boot.service` instead, and systemd dropped `network-pre.target`: boot finished and cloud-init reported `done`, but `systemd-networkd` started about 1.9 seconds before Foomuuri, which fails RN-FW-04.

| Run | `network-pre.target` | Order | Boot | RN-FW-04 |
| --- | --- | --- | --- | --- |
| No drop-in | Reached | Foomuuri before the network | Never finished, `cloud-init-network` dropped | At risk |
| Drop-in on `foomuuri.service` only | `0`, dropped | `systemd-networkd` 1.9 s before Foomuuri | `running` | Not met |
| Drop-in on both units | Reached | Foomuuri before the network | `running` | Met |

The install step puts the drop-in on both units before Foomuuri is enabled, so a clean run has no cycle and the check above passes the first time. On a container set up with an earlier version of this spike, push the drop-ins now, then restart and check again:

```sh
for u in foomuuri foomuuri-boot; do
  incus file push "spike-files/optional/etc/systemd/system/${u}.service.d/10-raw-node.conf" \
    "${I}/etc/systemd/system/${u}.service.d/10-raw-node.conf" --project spike-incus \
    --uid 0 --gid 0 --mode 0644 --create-dirs
done
incus restart "${I}" --project spike-incus
sleep 3
incus exec "${I}" --project spike-incus -- sh -c '
  timeout 120 systemctl is-system-running --wait
  systemctl list-jobs --no-pager
  cloud-init status
  systemctl show --property=Id,ActiveEnterTimestampMonotonic \
    foomuuri-boot.service foomuuri.service network-pre.target \
    systemd-networkd.service cloud-init-network.service
'
```

Output:

```bash
running
No jobs running.
status: done
Id=foomuuri-boot.service
ActiveEnterTimestampMonotonic=156666989978

Id=foomuuri.service
ActiveEnterTimestampMonotonic=156667197393

Id=network-pre.target
ActiveEnterTimestampMonotonic=156667210181

Id=systemd-networkd.service
ActiveEnterTimestampMonotonic=156667252342

Id=cloud-init-network.service
ActiveEnterTimestampMonotonic=156668619482
```

| Unit Order | Active at (µs, host clock) | After the previous unit |
| --- | --- | --- |
| `foomuuri-boot.service` | 156666989978 | |
| `foomuuri.service` | 156667197393 | 0.21 s |
| `network-pre.target` | 156667210181 | 13 ms |
| `systemd-networkd.service` | 156667252342 | 42 ms |
| `cloud-init-network.service` | 156668619482 | 1.4 s |

RN-FW-04 is met: boot finishes, no job is dropped, cloud-init reports `done`, and Foomuuri is active before `network-pre.target` and `systemd-networkd`. A `0` for `network-pre.target` or `cloud-init-network.service` would mean systemd still dropped a job to break a cycle.

Netfilter is namespaced, so an unprivileged container is expected to have its own working ruleset <a id="cite-forum-nft-unpriv"></a>([How does nftables work, n.d.](#ref-forum-nft-unpriv)). The spike confirms this on your host and kernel.

### Decision gate for the firewall

| Observation | Meaning | Action |
| --- | --- | --- |
| Foomuuri active, only `table inet foomuuri`, port 22 open, port 8080 blocked, no ordering cycle | The raw node firewall works in an unprivileged container | Proceed and record it in the coverage table |
| Foomuuri active but `SSH RULE MISSING` | The service ran but the raw node rules are not loaded | Run `foomuuri check` in the container, and compare `/etc/foomuuri/00-raw-node.conf` with the archive using `sha256sum` |
| An ordering cycle in the journal, boot that never finishes with a cloud-init job stuck, or `network-pre.target` at `0` | RN-FW-04 is at risk or fails on this image. In a container the cycle may not appear in the journal, and `systemd-analyze verify` did not show it either. | Push the optional drop-in for both Foomuuri units, and record that the Incus backend needs it |
| `foomuuri.service` fails with `Failed to set up mount namespacing` | The unit's systemd sandboxing is refused inside the container, not the firewall itself | Record it; see [If the ruleset does not load](#if-the-ruleset-does-not-load) |
| `Operation not permitted` when the ruleset loads | The container lacks a capability nftables needs | See [If the ruleset does not load](#if-the-ruleset-does-not-load) |
| `Protocol not supported` | The host kernel has not loaded `nf_tables` | On the host, check `lsmod \| grep nf_tables` and load it with `modprobe nf_tables` |
| Rules listed but port 8080 still answers from the host | Rules load but are not enforced | Record it as a limitation; containers cannot be raw nodes without enforcement on the host |

A sandboxing failure of this kind has been reported for `nftables.service` in Proxmox LXC containers, where `nft` itself worked <a id="cite-proxmox-nft"></a>([lethargos, n.d.](#ref-proxmox-nft)). It may or may not occur for Foomuuri under Incus, which is why the gate checks the service and the ruleset separately.

### If the ruleset does not load

Check what the container's init process holds:

```sh
incus exec "${I}" --project spike-incus -- grep Cap /proc/1/status
```

Decode `CapEff` with `capsh --decode=<value>` on the host and look for `cap_net_admin`.

Incus has no option that grants a single capability. Containers are unprivileged unless `security.privileged` is set explicitly <a id="cite-forum-privileged"></a>([How to find out the LXC privilege, n.d.](#ref-forum-privileged)), and the other way round restrictions is low-level `raw.lxc` configuration. Both weaken isolation, so neither belongs quietly in the backend's settings. If one of them is the only way to load the ruleset, record it and open a contract review instead, as RB-04 requires.

## Check MAC stability

Read the MAC address inside the container, restart, and read it again:

```sh
incus exec "${I}" --project spike-incus -- cat /sys/class/net/eth0/address
echo "Expected: ${TEST_MAC}"
incus restart "${I}" --project spike-incus
sleep 5
incus exec "${I}" --project spike-incus -- cat /sys/class/net/eth0/address
```

Output example:

```bash
Expected: 02:aa:bb:cc:dd:01
02:aa:bb:cc:dd:01
```

Then test an automatically assigned address. Incus records it in the instance's `volatile.eth0.hwaddr` key:

```bash
incus launch images:debian/13/cloud deb13-ic-auto \
  --project spike-incus \
  --config cloud-init.user-data="$(cat spike-user-data.yml)"
```

output:

```bash
Launching deb13-ic-auto
```

then:

```bash
incus config get deb13-ic-auto volatile.eth0.hwaddr --project spike-incus
```

Output example:

```bash
10:66:6a:a3:42:1b
```

then:

```bash
incus launch images:debian/13/cloud deb13-ic-auto \
  --project spike-incus \
  --config cloud-init.user-data="$(cat spike-user-data.yml)"
```

output:

```bash
Error: Failed instance creation: Instance "deb13-ic-auto" already exists
```

then: 

```bash
incus exec deb13-ic-auto --project spike-incus -- cat /sys/class/net/eth0/address
```

Output:

```bash
10:66:6a:d4:16:2c
```

```sh
incus restart deb13-ic-auto --project spike-incus
sleep 5
incus exec deb13-ic-auto --project spike-incus -- cat /sys/class/net/eth0/address
```

The second `incus launch` of `deb13-ic-auto` above is not needed: the instance already exists, and the error is harmless. In the first run the automatic address `10:66:6a:d4:16:2c` matched `volatile.eth0.hwaddr` and was reported unchanged after the restart, but that output was not recorded. Record it in the clean run.

An instance with an overridden `hwaddr` has no `volatile.eth0.hwaddr` key, because the override replaces the profile device <a id="cite-forum-hwaddr"></a>([Howto add hwaddr, n.d.](#ref-forum-hwaddr)). That is expected for `deb13-ic-dd01`.

### Decision gate for MAC stability

| Observation | Meaning |
| --- | --- |
| The fixed address matches `TEST_MAC` and survives a restart | Explicit assignment works and the hostname is known before launch |
| The automatic address matches `volatile.eth0.hwaddr` and survives a restart | The backend could let Incus choose and read the address afterwards, though explicit assignment stays preferable because the name is known in advance |
| Either address changes after a restart | The suffix is not stable; record it and review the hostname rule |

## Test report retrieval

RB-07 asks for the report to be fetchable without logging in where the platform allows it. For a container, Incus reads the file from the host:

```sh
incus file pull "${I}/var/lib/raw-node/confirmation.yml" ./confirmation.yml --project spike-incus
cat ./confirmation.yml
```

Output example:

```bash
deb13-ic-dd01:
  contract: 0.3.0
  baseline: 0.4.0
  timestamp: 2026-11-21T01:27:32+00:00
  machine_id: "a5ba0ec47ad341e98f6d7fecf523af14"
  user: initial
  sudo: true
  sudo_nopasswd: false
  ssh_port: 22
  ssh_password_auth: false
  ssh_host_keys:
    - type: ecdsa-sha2-nistp256
      fingerprint: "SHA256:aiSZhtIWZ1kSJGTBRrTUV+fF/agK//1Y8M0pciCp/8o"
    - type: ssh-ed25519
      fingerprint: "SHA256:icKO9dvaEgSQnxaNhMRSwNErEdRBOFUeNUitQDnq0AU"
    - type: ssh-rsa
      fingerprint: "SHA256:r+b4+6DStEGo8wlT7xA/aiDDnf31XciXU+QmghcX3Es"
  firewall: foomuuri
  firewall_active: true
  python: /usr/bin/python3
  interfaces:
    - name: eth0
      type: other
      mac: "02:aa:bb:cc:dd:01"
      state: up
      default_route4: true
      default_route6: false
      ip: [10.119.134.150]
      ip6: []
```

If the file arrives with no login to the container, RB-07 is met for containers.

## Walk the contract clauses

These are the checks in "Checks on an installed node" in uc-ventoy's `en/docs/contracts.md`, adapted to `incus exec`. Run them as root inside the container:

```sh
incus exec "${I}" --project spike-incus -- sh -c '
  stat -c "%a %U" /var/lib/raw-node/confirmation.yml
  python3 -c "import yaml; print(yaml.safe_load(open(\"/var/lib/raw-node/confirmation.yml\")))"
  grep RAW_NODE /etc/raw-node/raw-node.conf
  hostnamectl --static
  ls -la /home/initial /home/initial/.ssh
  passwd -S root
  grep -r -n -E "NOPASSWD|!authenticate" /etc/sudoers /etc/sudoers.d
  ls -la /etc/sudoers-rs 2>/dev/null
  sshd -T | grep -E "^(port|permitrootlogin|pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|permitemptypasswords) "
  ls /etc/ssh/sshd_config.d/
  for f in /etc/ssh/ssh_host_*_key.pub; do ssh-keygen -l -f "$f"; done
  ss -ltnp | grep -E "sshd|systemd"
  iptables-legacy-save 2>/dev/null | grep -c "^-A"
  sha256sum /etc/ssh/sshd_config.d/10-local-auth.conf /etc/ssh/sshd_config.d/20-raw-node-port.conf \
    /etc/foomuuri/00-raw-node.conf /usr/local/sbin/raw-node-report /usr/local/sbin/raw-node-firstboot \
    /etc/systemd/system/raw-node-firstboot.service
'
```

Output:

```bash
644 root
{'deb13-ic-dd01': {'contract': '0.3.0', 'baseline': '0.4.0', 'timestamp': datetime.datetime(2026, 11, 21, 1, 27, 32, tzinfo=datetime.timezone.utc), 'machine_id': 'a5ba0ec47ad341e98f6d7fecf523af14', 'user': 'initial', 'sudo': True, 'sudo_nopasswd': False, 'ssh_port': 22, 'ssh_password_auth': False, 'ssh_host_keys': [{'type': 'ecdsa-sha2-nistp256', 'fingerprint': 'SHA256:aiSZhtIWZ1kSJGTBRrTUV+fF/agK//1Y8M0pciCp/8o'}, {'type': 'ssh-ed25519', 'fingerprint': 'SHA256:icKO9dvaEgSQnxaNhMRSwNErEdRBOFUeNUitQDnq0AU'}, {'type': 'ssh-rsa', 'fingerprint': 'SHA256:r+b4+6DStEGo8wlT7xA/aiDDnf31XciXU+QmghcX3Es'}], 'firewall': 'foomuuri', 'firewall_active': True, 'python': '/usr/bin/python3', 'interfaces': [{'name': 'eth0', 'type': 'other', 'mac': '02:aa:bb:cc:dd:01', 'state': 'up', 'default_route4': True, 'default_route6': False, 'ip': ['10.119.134.150'], 'ip6': []}]}}
RAW_NODE_USER=initial
RAW_NODE_TARGET=incus/debian/13
RAW_NODE_BASELINE=0.4.0
RAW_NODE_CONTRACT=0.3.0
deb13-ic-dd01
/home/initial:
total 12
drwx------ 1 initial initial   62 Nov 21 01:21 .
drwxr-xr-x 1 root    root      14 Nov 21 01:21 ..
-rw-r--r-- 1 initial initial  220 Jul 12 16:58 .bash_logout
-rw-r--r-- 1 initial initial 3526 Jul 12 16:58 .bashrc
-rw-r--r-- 1 initial initial  807 Jul 12 16:58 .profile
drwx------ 1 initial initial   30 Nov 21 01:21 .ssh

/home/initial/.ssh:
total 4
drwx------ 1 initial initial 30 Nov 21 01:21 .
drwx------ 1 initial initial 62 Nov 21 01:21 ..
-rw------- 1 initial initial 96 Nov 21 01:21 authorized_keys
root P 2026-11-21 0 99999 7 -1
port 22
permitrootlogin no
pubkeyauthentication yes
passwordauthentication no
kbdinteractiveauthentication no
permitemptypasswords no
10-local-auth.conf  20-raw-node-port.conf
256 SHA256:aiSZhtIWZ1kSJGTBRrTUV+fF/agK//1Y8M0pciCp/8o root@deb13-ic-dd01 (ECDSA)
256 SHA256:icKO9dvaEgSQnxaNhMRSwNErEdRBOFUeNUitQDnq0AU root@deb13-ic-dd01 (ED25519)
3072 SHA256:r+b4+6DStEGo8wlT7xA/aiDDnf31XciXU+QmghcX3Es root@deb13-ic-dd01 (RSA)
LISTEN 0      4096   127.0.0.53%lo:53        0.0.0.0:*    users:(("systemd-resolve",pid=154,fd=18))
LISTEN 0      128          0.0.0.0:22        0.0.0.0:*    users:(("sshd",pid=230,fd=6))            
LISTEN 0      4096         0.0.0.0:5355      0.0.0.0:*    users:(("systemd-resolve",pid=154,fd=12))
LISTEN 0      4096      127.0.0.54:53        0.0.0.0:*    users:(("systemd-resolve",pid=154,fd=20))
LISTEN 0      128             [::]:22           [::]:*    users:(("sshd",pid=230,fd=7))            
LISTEN 0      4096            [::]:5355         [::]:*    users:(("systemd-resolve",pid=154,fd=14))
0
3e852684408dbc683ed6edd453eae4e09d6118218fdd198d6ab785e36831fb0c  /etc/ssh/sshd_config.d/10-local-auth.conf
6d73d8829982d450c2db2c1bf35bb96a3e7308a1419001f343c1725d6f09c526  /etc/ssh/sshd_config.d/20-raw-node-port.conf
ff3ebd713c3bac379e7b8933d32e0ed183619a17c4212c4b613ef79c30c7b823  /etc/foomuuri/00-raw-node.conf
084348b8da5011abab4b14002dcc1b4d4551d3dda391adce093aeaa092ff188e  /usr/local/sbin/raw-node-report
e63c4c47af5da96702f46b1411dd9cceaa0b7b9e71aa79907f2712b7bf7df8ce  /usr/local/sbin/raw-node-firstboot
52424dcfb326f25db12028c17339c19f8846d43c198e1d357557f08c591569cc  /etc/systemd/system/raw-node-firstboot.service

```

Compare the `sha256sum` output with the same files on the reference node. Then, from the host:

you may need to do this first

```bash
ssh-keygen -f '/home/initial/.ssh/known_hosts' -R '10.119.134.150'
```

then:

```sh
# RN-ACC-02: must log in with the key
ssh -o PreferredAuthentications=publickey initial@"${IP}" true
# RN-SSH-03, RN-ACC-05: both refused with "Permission denied (publickey)", without a password prompt
ssh -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no initial@"${IP}" true
ssh -o PreferredAuthentications=password,keyboard-interactive -o PubkeyAuthentication=no root@"${IP}" true
# RN-ACC-04: must ask for the password, and accept it
ssh -t initial@"${IP}" 'sudo -k; sudo true'
# Host keys: must match ssh_host_keys in the report
ssh-keyscan "${IP}" 2>/dev/null | ssh-keygen -l -f -
```

Output:

```bash
The authenticity of host '10.119.134.150 (10.119.134.150)' can't be established.
ED25519 key fingerprint is SHA256:icKO9dvaEgSQnxaNhMRSwNErEdRBOFUeNUitQDnq0AU.
This key is not known by any other names.
Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
Warning: Permanently added '10.119.134.150' (ED25519) to the list of known hosts.
Received disconnect from 10.119.134.150 port 22:2: Too many authentication failures
Disconnected from 10.119.134.150 port 22
initial@10.119.134.150: Permission denied (publickey).
root@10.119.134.150: Permission denied (publickey).
Received disconnect from 10.119.134.150 port 22:2: Too many authentication failures
Disconnected from 10.119.134.150 port 22
3072 SHA256:r+b4+6DStEGo8wlT7xA/aiDDnf31XciXU+QmghcX3Es 10.119.134.150 (RSA)
256 SHA256:aiSZhtIWZ1kSJGTBRrTUV+fF/agK//1Y8M0pciCp/8o 10.119.134.150 (ECDSA)
256 SHA256:icKO9dvaEgSQnxaNhMRSwNErEdRBOFUeNUitQDnq0AU 10.119.134.150 (ED25519)
```

For RN-ACC-06, log in as `initial` with its password at the console, which `incus console "${I}" --project spike-incus` opens. Leave it with `Ctrl+a q`.

```bash
incus console "${I}" --project spike-incus
```

Output:

```bash
initial
Password: 
Linux deb13-ic-dd01 7.0.0-43-generic #43~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC Sat Oct 31 06:52:47 UTC 2 x86_64

The programs included with the Debian GNU/Linux system are free software;
the exact distribution terms for each program are described in the
individual files in /usr/share/doc/*/copyright.

Debian GNU/Linux comes with ABSOLUTELY NO WARRANTY, to the extent
permitted by applicable law.
initial@deb13-ic-dd01:~$ 
```

Then to exit the console:

```bash
<ctrl>+a q 
```

Then fill in one row per clause:

| Clause | Subject | Container result | Evidence |
| --- | --- | --- | --- |
| RN-NET-01 | Hostname set, not the installer default | Met | `hostnamectl --static` |
| RN-ACC-01 | Initial user's home holds only `.ssh/authorized_keys` and defaults | Met | `ls -la /home/initial` |
| RN-ACC-02 | Key login over SSH | Met | Key login works |
| RN-ACC-04 | sudo with the password | Met | `sudo` asks and accepts |
| RN-ACC-05 | Root has a password and no SSH login | Met | `passwd -S root` reports `P`, root SSH refused |
| RN-ACC-06 | Console login with the batch password | Met | `incus console` login |
| RN-ACC-07 | No passwordless sudo rule | Met | `grep` finds nothing, `sudo_nopasswd: false` |
| RN-ACC-08 | Batch password procedure | Met by procedure | Met by procedure |
| RN-SSH-01 | SSH listens on `ssh_port` | Met | `ss -ltnp` |
| RN-SSH-02 | SSH reachable from `ssh_sources` | Met | `nc` and `nmap` from the host |
| RN-SSH-03 | Password login over SSH refused | Met | Both password attempts refused |
| RN-FW-01 | nftables is the only packet filter | Met | `nft list tables`, `iptables-legacy-save` count 0 |
| RN-FW-02 | One manager, one table, no full flush | Met | `nftables.service` masked, only `table inet foomuuri` |
| RN-FW-03 | Only SSH, DHCP, ping and needed ICMP in | Met | [Decision gate for the firewall](#decision-gate-for-the-firewall) |
| RN-FW-04 | Firewall in force before the network | Met with the drop-in on both Foomuuri units | Activation times, `network-pre.target` reached, boot `running` |
| RN-REP-01 | `confirmation.yml` with the contract fields | Met | Mode `644`, fields present |

Where a clause assumes something the node owns, these checks show whether a container owns it:

| Assumption | Check in the container | Expected in a container |
| --- | --- | --- |
| Own kernel | `uname -r`, compared with the host | Same as the host |
| Boot loader | `ls /boot` | Empty or absent |
| Disk partitioning | `df -h /` | A storage pool volume, not a partition |
| Hardware | `ls /sys/bus/pci/devices` | Empty |

For each clause a container cannot meet by its nature, record it in this form for the contract review:

```text
RN-XXX-NN: Not applicable to containers.
Reason: The host provides <kernel | boot loader | disk | hardware | network>.
Proposed contract change: Scope RN-XXX-NN to nodes that own their <...>,
or add "Container-delivered nodes are exempt from RN-XXX-NN."
```

This is the route RB-04 sets out: when a platform cannot meet a requirement, the requirement is reviewed in the contract rather than worked around in the backend.

In this run no clause failed by nature. The console login shows the host's kernel, `7.0.0-43-generic`, as expected for a container, and no clause depends on the node owning its kernel, boot loader, disk or hardware.

## Compare with a virtual machine

Optionally, repeat the launch with `--vm` and the same user data, then the same checks. Virtual machines rely on `incus-agent` for cloud-init, exec and file operations, and images from the `images:` remote already include it ([Linux Containers, n.d.-b](#ref-incus-cloudinit)). This shows whether a VM-only Incus backend would meet every clause without contract changes.

## Clean up

```sh
incus delete --force deb13-ic-dd01 deb13-ic-auto --project spike-incus
incus project delete spike-incus
rm -rf spike-user-data.yml confirmation.yml spike-files
```

`spike-user-data.yml` holds password hashes, so delete it.

## Results template

Fill this in from the clean run and copy it into the Incus backend document.

```markdown
## Spike results, YYYY-MM-DD

Host: <hostname>, <distribution>, Incus <version>, kernel <version>
Image: images:debian/13/cloud
Node files: uc-ventoy 5ed7bb8, baseline 0.4.0, contract 0.3.0
Container mode: unprivileged, no security options changed

| Question | Result | Notes |
| --- | --- | --- |
| Bridge provides IPv6? | Yes, no | |
| Foomuuri active, only table inet foomuuri? | Yes, no, needs privilege | |
| Ruleset enforced (8080 blocked, 22 open)? | Yes, no | |
| Ordering cycle at boot? | Yes, no, fixed by drop-in | |
| Fixed MAC stable across restart? | Yes, no | |
| Automatic MAC stable across restart? | Yes, no | |
| Hostname after first boot | <value> | |
| confirmation.yml written at boot? | Yes, no | |
| incus file pull retrieves report? | Yes, no | |
| Checksums match the reference node? | Yes, no | |
| Clauses needing contract review | RN-XXX-NN | |

Decision:

- [ ] Containers supported with no privilege changes
- [ ] Containers supported only after a contract amendment
- [ ] Containers not supported; the Incus backend is VM-only
```

## Results of the run on 2026-11-20

Host: Ubuntu 24.04 with kernel 7.0.0-43-generic, Incus <version>
Image: images:debian/13/cloud, serial 20261118_05:24
Node files: uc-ventoy 5ed7bb8, baseline 0.4.0, contract 0.3.0
Container mode: unprivileged, no security options changed

| Question | Result | Notes |
| --- | --- | --- |
| Bridge provides IPv6? | Yes | `fd42:48:ed9e:b152::1/64` |
| Foomuuri active, only table inet foomuuri? | Yes | `nftables.service` masked, only `00-raw-node.conf` |
| Ruleset enforced (8080 blocked, 22 open)? | Yes | Listener answers `200` inside, `curl` from the host times out, `nmap` shows only 22 open |
| Ordering cycle at boot? | Yes, fixed by the drop-in on both Foomuuri units | Not in the journal. Without a drop-in `cloud-init-network` was dropped and boot never finished. With it on `foomuuri.service` only, `network-pre.target` was dropped and the network came up 1.9 s before the firewall. |
| Fixed MAC stable across restart? | Yes | `02:aa:bb:cc:dd:01` |
| Automatic MAC stable across restart? | Yes | Matched `volatile.eth0.hwaddr`, reported unchanged after a restart; output to record in the clean run |
| Hostname after first boot | `deb13-ic-dd01` | Unchanged, `raw-node-firstboot` only suffixes `-vt` |
| confirmation.yml written at boot? | Yes | After `openssh-server` was added; `ip6` empty because the report ran before SLAAC completed |
| incus file pull retrieves report? | Yes | RB-07 met |
| Checksums match the reference node? | Yes | All six match uc-ventoy `5ed7bb8` |
| Clauses needing contract review | None | |

Findings for the Incus backend:

- The cloud image has no `openssh-server`, so the backend's user data must install it.
- `raw-node-firstboot` only suffixes `-vt` hostnames, so the backend names instances with the MAC suffix at launch, or the script learns `-ic`.
- The report can run before SLAAC completes and miss IPv6. The backend, or `raw-node-firstboot`, may wait for an IPv6 address when the bridge provides one.
- `type: other` for `eth0`, a UTC timestamp and three host keys are normal for this image in a container.
- The Debian cloud image needs the Foomuuri drop-in on both `foomuuri.service` and `foomuuri-boot.service`. Without it, Foomuuri and cloud-init form an ordering cycle. With it on `foomuuri.service` alone, as uc-ventoy's Ubuntu targets have it, the cycle runs through `foomuuri-boot.service` and the network starts before the firewall. In a container the cycle shows neither in the journal nor in `systemd-analyze verify`.
- For uc-ventoy: any cloud-init target whose Foomuuri has `foomuuri-boot.service` needs the drop-in on both units. Debian 13 ships Foomuuri 0.27, which has it. Check whether Ubuntu 26.04's Foomuuri does, and check RN-FW-04 on a real 26.04 install by activation times, including that `network-pre.target` is not `0`.
- Anything in the backend that waits for boot or for `cloud-init status --wait` hangs while the cycle is present.
- The cloud image runs `systemd-resolved` with LLMNR on port 5355 on all addresses. The firewall blocks it from outside, but a node installed with the Debian installer does not run it.

Decision, pending the clean run:

- [x] Containers supported with no privilege changes
- [ ] Containers supported only after a contract amendment
- [ ] Containers not supported; the Incus backend is VM-only

## What comes next

Run the spike once more from a clean start, following this version from top to bottom, and fill in the results template. The first run reached its result through fixes applied one at a time to the same container. A clean run shows that the procedure works as written, that the first boot with Foomuuri enabled and both drop-ins in place finishes, and that nothing depended on state left by earlier steps.

The spike shows that an unprivileged container can be a raw node, with files pushed by hand. It does not yet show that the Incus backend can deliver the same node from cloud-init user data alone: installing the packages, writing the canonical files and both drop-ins, masking `nftables.service` and enabling the units, with package installation happening partway through the first boot. That is the first thing to prototype for the backend.

If containers pass, write the Incus backend: the code that creates instances with the right configuration, delivers the canonical files and both Foomuuri drop-ins through cloud-init before Foomuuri is enabled, waits for cloud-init and fetches `confirmation.yml`.

If any clause fails by nature, open a contract review item with the clause, the reason and the proposed wording.

If Foomuuri cannot load or enforce the ruleset without privilege, make the Incus backend VM-only and leave containers for a later backend.

## References

<a id="ref-cloudinit-setpasswords"></a>cloud-init. (n.d.-a). *cc_set_passwords.py* (Version 25.3) [Source code]. Debian Sources. https://sources.debian.org/src/cloud-init/25.3-2/cloudinit/config/cc_set_passwords.py
[Return to citation](#cite-cloudinit-setpasswords)

<a id="ref-cloudinit-users"></a>cloud-init. (n.d.-b). *Configure users and groups* (Version 25.3). cloud-init documentation. https://docs.cloud-init.io/en/25.3/reference/yaml_examples/user_groups.html
[Return to citation](#cite-cloudinit-users)

<a id="ref-forum-nft-unpriv"></a>*How does nftables work inside an unpriviledged container?* (n.d.). [Online forum post]. Linux Containers Forum. https://discuss.linuxcontainers.org/t/how-does-nftables-work-inside-an-unpriviledged-container/14409
[Return to citation](#cite-forum-nft-unpriv)

<a id="ref-forum-privileged"></a>*How to find out the LXC privilege?* (n.d.). [Online forum post]. Linux Containers Forum. https://discuss.linuxcontainers.org/t/how-to-find-out-the-lxc-privilege/20975
[Return to citation](#cite-forum-privileged)

<a id="ref-forum-hwaddr"></a>*Howto add hwaddr to nic created with profile?* (n.d.). [Online forum post]. Linux Containers Forum. https://discuss.linuxcontainers.org/t/howto-add-hwaddr-to-nic-created-with-profile/9714
[Return to citation](#cite-forum-hwaddr)

<a id="ref-incus-device-flag"></a>*Incus init: How to correctly pass the network configuration to "incus init --device ..."?* (n.d.). [Online forum post]. Linux Containers Forum. https://discuss.linuxcontainers.org/t/incus-init-how-to-correctly-pass-the-network-configuration-to-incus-init-device/25943
[Return to citation](#cite-incus-device-flag)

<a id="ref-proxmox-nft"></a>lethargos. (n.d.). *Run nftables in debian 12 lxc-container* [Online forum post]. Proxmox Support Forum. https://forum.proxmox.com/goto/post?id=650497
[Return to citation](#cite-proxmox-nft)

<a id="ref-incus-projects-create"></a>Linux Containers. (n.d.-a). *How to create and configure projects*. Incus documentation. https://linuxcontainers.org/incus/docs/main/howto/projects_create/
[Return to citation](#cite-incus-projects-create)

<a id="ref-incus-cloudinit"></a>Linux Containers. (n.d.-b). *How to use cloud-init*. Incus documentation. https://linuxcontainers.org/incus/docs/main/cloud-init/
[Return to citation](#cite-incus-cloudinit)

<a id="ref-incus-projects"></a>Linux Containers. (n.d.-c). *Project configuration*. Incus documentation. https://linuxcontainers.org/incus/docs/main/reference/projects/
[Return to citation](#cite-incus-projects)

<a id="ref-incus-nic"></a>Linux Containers. (n.d.-d). *Type: nic*. Incus documentation. https://linuxcontainers.org/incus/docs/main/reference/devices_nic/
[Return to citation](#cite-incus-nic)

## Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.2.18 | 2026-11-20 | Prepared for a clean confirming run: the Foomuuri drop-ins for both units are pushed in the install step, before Foomuuri is enabled, and the firewall section's push is kept for containers set up with an earlier version. A clean-slate note before creating the project. The automatic MAC result recorded as reported. What comes next explains the clean run and what the spike does not yet cover for the backend. |
| 0.2.17 | 2026-11-20 | RN-FW-04 met. On Debian 13 the Foomuuri drop-in is needed on both `foomuuri.service` and `foomuuri-boot.service`: with it on `foomuuri.service` only, systemd dropped `network-pre.target` and the network started 1.9 s before the firewall. Added the unit-file evidence for the cycle, a table of the three runs, the fix for both units with its output, and the activation-time table. Updated the gate, clause table, results, findings (including one for uc-ventoy's cloud-init targets) and the archive's `optional/` folder. |
| 0.2.16 | 2026-11-20 | Diagnosed boot never finishing: Foomuuri and cloud-init form the ordering cycle the uc-ventoy Ubuntu targets fix with a drop-in, systemd drops `cloud-init-network.service`, and `cloud-config` waits for ever. The cycle does not show in a container's journal. Added the diagnosis, a `systemd-analyze verify` check and the drop-in fix with its check, and updated the firewall gate, clause table, results and findings. Corrected the statement that the Debian cloud image does not need the drop-in, and the activation time table, which now uses the times in its output example and labels them microseconds. |
| 0.2.15 | 2026-11-20 | Output of the bounded RN-FW-04 check, a worked table of activation times, and a note on how long the check takes. |
| 0.2.14 | 2026-11-20 | The RN-FW-04 step bounds its wait with `timeout 120`, lists queued jobs, and reads the order of Foomuuri and the network from activation times, after `systemctl is-system-running --wait` waited without end and `critical-chain` cannot answer before boot finishes. The listener note and results record the `systemd-run` listener answering `200` inside while blocked from the host. |
| 0.2.13 | 2026-11-20 | Output of the firewall enforcement test with the `systemd-run` listener. |
| 0.2.12 | 2026-11-20 | Results of the container run: clause table filled in, a results section with findings for the Incus backend, and the IPv6 result (timing, not the firewall). The test listener starts with `systemd-run`, because `nohup` ended with the exec session. The RN-FW-04 check waits for boot to finish. Notes on the repeated launch and the missing automatic MAC restart output. Checksums confirmed against uc-ventoy `5ed7bb8`. |
| 0.2.11 | 2026-11-20 | Output from the full container run: IPv6 check, missing-report check, firewall, MAC stability, report retrieval, contract checks, SSH tests and console login. |
| 0.2.10 | 2026-11-20 | Replaced the placeholder report example with a table of what the real report shows: three host keys named as OpenSSH names them, `type: other` for a container's `eth0`, a UTC timestamp and no IPv6. Added a check of whether the missing IPv6 is timing or the firewall, and a heading for the missing-report steps. |
| 0.2.9 | 2026-11-20 | The real report from a run as the output example of the restart and wait step, and new test hashes in the real world example. |
| 0.2.8 | 2026-11-20 | The wait loop keeps waiting until the unit is `active` or `failed`, after a run where `systemctl` could not reach systemd just after the restart and the loop ended at once. Quoted the hashes in the real world example and added a check that both hashes reached the user data. Removed a duplicated enable and restart block. |
| 0.2.7 | 2026-11-20 | Output examples from a run, a real world example of the user data, a step that deletes an instance left over from an earlier run, and the enable and restart steps split with their output. |
| 0.2.6 | 2026-11-20 | Adds `openssh-server` to the user data, after a run found the cloud image has no `sshd` and the report failed with status 2. Waits for the first-boot unit to finish instead of 5 seconds, reads its journal instead of `report.err`, and adds a table of report failures. |
| 0.2.5 | 2026-11-20 | Brought in line with uc-ventoy baseline 0.4.0 and contract 0.3.0. The firewall is Foomuuri, with `nftables.service` masked, and the firewall section and gate test RN-FW-01 to RN-FW-04, including the boot ordering cycle. The canonical files come from `uc-ventoy-spike-files.tar.gz` and its manifest, including the new port drop-in. The report example has the contract 0.3.0 fields. SSH password login is now expected to be refused. RN-01 to RN-12 replaced by the contract 0.3.0 clauses and the checks in `contracts.md`. Fixed the quoting of existing hashes and replaced the real hashes with placeholders. Records that `raw-node-firstboot` only suffixes `-vt` hostnames. |
| 0.2.4 | 2026-11-20 | Output examples from a run, and an example with edited values. |
| 0.2.3 | 2026-11-20 | Runs the first-boot unit with `restart` instead of `start`, and shows its status. |
| 0.2.2 | 2026-11-20 | Added a check of how `raw-node-firstboot.service` decides to run, with `systemctl start` as a fallback. |
| 0.2.1 | 2026-11-20 | Added an IPv6 check on the bridge, an assertion that the bootstrap rules are loaded, a note on how `--device` merges with the profile device, and a note on `raw-node.conf` target mismatches. |
| 0.2.0 | 2026-11-20 | Cleaned up for the web with APA 7 citations. Corrected the project options, the MAC option (`hwaddr` instead of `security.mac_address`), the `MAC4` calculation, the cloud-init user data and root password, and the cleanup commands. Replaced the simulated report with the canonical first-boot files, the `security.capability` step with a capability check, and the invented RN rows with the real RN-01 to RN-12. Added an enforcement test for `nftables`. |
| 0.1.0 | 2026-11-20 | First draft. |

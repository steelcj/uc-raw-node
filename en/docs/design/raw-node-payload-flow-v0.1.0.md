# Raw Node Payload Flow

- **Version:** 0.1.0
- **Date:** 2026-11-22
- **License:** Proprietary / Internal Use Only
- **Author:** Christopher Steel

## Purpose

This chart shows how `build.yml` builds the `raw-node-adopt` payload on the controller host, drops it into a Debian 13 Incus container and gets the node's confirmation back, for the priority 1 platform `incus_container_default`. The steps marked new are not in the code at `v0.3.0`. Launch, push, run, failure handling and teardown already work.

## Flow

```mermaid
flowchart TD
    subgraph host["Controller host"]
        inputs["Inputs<br/>raw-node-input.yml, registry entry,<br/>uc-ventoy node files"]
        checks["build.yml checks<br/>registry, input, platform,<br/>output paths, attempt record"]
        render["payload.yml renders raw-node-adopt (new)<br/>one self-contained script, mode 0600,<br/>in ~/.secrets/uc-raw-node/HOSTNAME/"]
        launch["Launch<br/>incus launch images:debian/13<br/>with the ownership marker"]
        push["Push and run<br/>incus file push, incus exec,<br/>then remove the staged script"]
        restart["Restart (new)<br/>incus restart"]
        pull["Pull (new)<br/>wait for confirmation.yml,<br/>incus file pull to reports/"]
        validate["Validate (new)<br/>raw_node_validator,<br/>clause by clause"]
        handoff["Hand-off<br/>records/HOSTNAME/confirmation.yml,<br/>attempt confirmed, secrets deleted"]
        failure["handle_failure.yml<br/>failure record, then destroy<br/>or quarantine"]
    end

    subgraph ct["Incus container"]
        fresh["Debian 13 container<br/>no cloud-init, no SSH server"]
        adopt["raw-node-adopt runs (new)<br/>packages, hostname, passwords,<br/>initial user and key, node files,<br/>enable foomuuri and raw-node-firstboot"]
        boot["First boot<br/>firewall up before the network,<br/>raw-node-firstboot writes<br/>/var/lib/raw-node/confirmation.yml"]
    end

    inputs --> checks --> render --> launch
    launch --> fresh
    launch --> push
    push --> adopt
    push --> restart
    restart --> boot
    boot --> pull
    pull --> validate --> handoff

    push -. fails .-> failure
    restart -. fails .-> failure
    pull -. no confirmation .-> failure
    validate -. clause fails .-> failure
```

## Notes

- **One file is the payload.** The two password hashes, the SSH public key and uc-ventoy's node files are written into `raw-node-adopt` itself, so the transport's existing push and run deliver it unchanged. The hashes reach `chpasswd -e` through the shell's `printf` built-in, never through a command line.
- **The restart makes it a raw node.** On that boot Foomuuri is in force before the network (RN-FW-04), and `raw-node-firstboot` measures the node and writes its confirmation (RN-REP-01).
- **The confirmation is the node's own.** The controller copies it to `records/` unchanged, so the orchestration controller receives exactly the contract's format.
- **Every failure goes the same way.** The failure record is written first, then the container is destroyed, or quarantined if teardown fails. The ownership marker means only a container this run created is ever deleted.

## Changes

### v0.1.0

- First version: the payload flow for `incus_container_default`, with the new steps marked and the failure paths.

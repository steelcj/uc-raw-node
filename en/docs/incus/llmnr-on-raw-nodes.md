---
title: "LLMNR on Raw Nodes"
version: "0.1.0"
date: 2026-11-20
author: "Christopher Steel"
status: "Draft, recommendation for review"
description: "What Link-Local Multicast Name Resolution is, why it is a known attack surface, where it appeared during the Incus container spike, and a recommendation for how raw nodes should handle it."
---

# LLMNR on Raw Nodes

## Summary

The Incus container spike found `systemd-resolved` listening for Link-Local Multicast Name Resolution (LLMNR) on port 5355 on all addresses of a node built from `images:debian/13/cloud`. The raw node firewall blocks the port from outside, so the node meets contract 0.3.0 as it stands. A node installed with the Debian installer does not run the service at all.

LLMNR answers name queries from anyone on the local network without any proof of identity, and poisoning it is a standard step in attacks on local networks. This document recommends that raw nodes keep it firewalled, as they already do, and also switch it off at the source, through a contract clause that every producer must meet.

## What LLMNR is

LLMNR lets machines on the same network segment find each other by name when no DNS server can answer. A machine that wants to reach `printer` sends the question to a multicast address, and whichever machine holds that name replies. It was written at Microsoft and published as an informational RFC in 2007 <a id="cite-rfc4795"></a>([Aboba et al., 2007](#ref-rfc4795)). It uses UDP and TCP port 5355, the IPv4 multicast address `224.0.0.252` and the IPv6 multicast address `ff02::1:3`.

The RFC treats it as a fallback. Queries are meant to go out only when DNS is not configured or has failed, by default only for single-label names such as `printer` rather than `printer.example.org`, and using LLMNR as the primary means of resolving names is not recommended. It works only on the local link, so it cannot replace DNS.

On Linux, `systemd-resolved` implements LLMNR, controlled by the `LLMNR=` setting in `resolved.conf`. The setting takes `yes`, `no` or `resolve`. `yes` turns on both the resolver and the responder, `no` turns off both, and `resolve` keeps the resolver but stops the node from answering. `systemd-networkd` also has a setting for each link, and LLMNR is used on a link only when both settings allow it <a id="cite-resolved-conf"></a>([Debian, n.d.](#ref-resolved-conf)).

## Why it is an attack surface

LLMNR has no way to tell a genuine answer from a forged one. The RFC itself says that an attacker on the same link is the larger concern, because multicast queries are visible to every machine on the link, so the attacker does not need to guess anything to reply. It offers authentication options, but only where keys or DNSSEC trust anchors have been arranged in advance, and the shared-key options do not stop one member of the group from forging answers for another ([Aboba et al., 2007](#ref-rfc4795)).

In practice this is exploited by poisoning. An attacker on the network answers every LLMNR query with its own address, the victim connects to the attacker believing it has reached the machine it asked for, and if that service asks for credentials the victim sends them. MITRE ATT&CK lists this as technique T1557.001 <a id="cite-mitre-t1557"></a>([MITRE, 2026](#ref-mitre-t1557)). Tools that automate it are freely available. Responder, the best known, answers LLMNR, NetBIOS and mDNS queries for names that do not exist and runs rogue authentication servers to collect credentials <a id="cite-responder"></a>([Gaffie, n.d.](#ref-responder)).

Most published advice is written for Windows, where LLMNR is on by default, but the advice holds for any host that answers or trusts LLMNR. MITRE's first mitigation is to disable LLMNR, mDNS and NetBIOS where they are not needed, followed by filtering the traffic on the host and segmenting the network. The US Cybersecurity and Infrastructure Security Agency (CISA) recommends disabling the LLMNR service entirely, and segmenting LLMNR networks from DNS networks where that is not possible <a id="cite-cisa-cm0053"></a>([CISA, 2025](#ref-cisa-cm0053)).

## Where it appeared

Debian has not made `systemd-resolved` its default resolver, and a node installed with the Debian installer does not run it. The Debian cloud images are built differently and do include it, which users have noticed and reported <a id="cite-debian-cloud-bug"></a>([flaviovs, 2024](#ref-debian-cloud-bug)). Debian 13 turned off mDNS resolution in `systemd-resolved` globally <a id="cite-debian-mdns"></a>([Crawford, 2025](#ref-debian-mdns)), which is why the spike found LLMNR on port 5355 but nothing on mDNS's port 5353.

On the spike's container, `ss -ltnp` showed `systemd-resolved` listening on `0.0.0.0:5355` and `[::]:5355`. From the host, `nmap` reported TCP 5355 as `filtered` and UDP 5355 as `open|filtered`, which for UDP is the answer expected for a port the firewall drops. The raw node firewall therefore stops other machines from querying the node's responder.

## What the firewall does and does not cover

The raw node firewall accepts SSH, DHCP and DHCPv6 replies, ping and the ICMP that networking needs, and drops all other inbound traffic, so the node's LLMNR responder cannot be reached from outside. That covers the node as a target of queries.

It leaves two gaps.

### The node as a client

With `LLMNR=yes`, the node itself sends LLMNR queries when DNS cannot answer a single-label name, such as a mistyped host in a script or a short name the DNS server does not know. The firewall accepts all outbound traffic, so those queries leave the node. Whether a forged reply gets back in depends on how connection tracking treats a unicast reply to a multicast query, and this has not been tested. If replies get in, any machine on the link can redirect the node's own connections.

### Later stages

The orchestration controller's customization stage will add rules and zones for the node's role, for example to accept traffic from an internal network. Port 5355 is not in any rule anyone will think to review, and a broader zone can expose the responder without any change to name resolution itself. A service that is switched off cannot be exposed by a later firewall change.

## Air-gapped node farms

An air-gapped farm is a case for keeping LLMNR only if its nodes must find each other by name with no DNS available. In a farm built by uc-raw-node and an orchestration controller, that need does not arise: the controller knows every node from its `confirmation.yml`, so it can write `/etc/hosts` on each node or run a small DNS server for the farm. Both give names that a neighbour cannot forge.

An air gap also does not remove the threat LLMNR is weak against. Poisoning needs only a machine on the same link, and in a farm that includes any one node that has been compromised, which can then redirect the name lookups of every other node.

## Recommendation

Keep the firewall rule as it is, and also require that raw nodes neither answer nor send LLMNR or mDNS queries.

### As a contract clause

Add a clause to the raw node contract rather than leaving the fix to the normalization stage. Written as an outcome, it applies to every producer whatever its resolver:

| Proposed ID | Clause |
| --- | --- |
| RN-NET-02 | The node neither answers nor sends Link-Local Multicast Name Resolution or multicast DNS queries |

A clause makes the protection hold from the first boot rather than from the first orchestration run, and it makes each producer state how it meets it. The Ventoy targets based on the Debian installer meet it because they do not run `systemd-resolved`. A producer whose image does run it, such as the Incus backend with the Debian cloud image, meets it with a drop-in. This fits RB-08, which forbids a backend from configuring anything beyond the raw node: once the clause exists, switching off LLMNR is part of the raw node.

### Implementation with systemd-resolved

Where `systemd-resolved` runs, a drop-in turns both protocols off:

```ini
# /etc/systemd/resolved.conf.d/10-raw-node.conf
# Raw node contract RN-NET-02: no LLMNR or mDNS, as resolver or responder.
[Resolve]
LLMNR=no
MulticastDNS=no
```

`MulticastDNS=no` repeats the Debian 13 default, so that the clause does not depend on a distribution default that may change. Apply it with:

```sh
systemctl restart systemd-resolved
```

### Checks

```sh
resolvectl status | grep -i -E "llmnr|mdns"
ss -lnup | grep -E ":5355|:5353" || echo "No LLMNR or mDNS listener"
ss -lntp | grep -E ":5355|:5353" || echo "No LLMNR or mDNS listener"
```

`resolvectl status` should show `-LLMNR` and `-mDNS` in its protocol list, and neither `ss` command should find a listener. On a node without `systemd-resolved`, `resolvectl` is absent and only the `ss` checks apply.

## Open points

- Whether the raw node firewall lets a forged unicast reply to the node's own multicast query back in. The recommendation does not depend on the answer, but the result belongs in the contract's notes on the firewall clauses.
- Whether the clause should also name NetBIOS Name Service. No raw node target runs it today.
- Whether the orchestration controller should keep the same drop-in in its normalization stage for nodes it adopts that were not produced by uc-raw-node.

## References

<a id="ref-rfc4795"></a>Aboba, B., Thaler, D., & Esibov, L. (2007). *Link-local Multicast Name Resolution (LLMNR)* (RFC 4795). RFC Editor. https://doi.org/10.17487/RFC4795
[Return to citation](#cite-rfc4795)

<a id="ref-cisa-cm0053"></a>Cybersecurity and Infrastructure Security Agency. (2025, March 14). *Disable Link-Local Multicast Name Resolution (LLMNR) service (CM0053)*. Eviction Strategies Tool. https://www.cisa.gov/eviction-strategies-tool/info-countermeasures/CM0053
[Return to citation](#cite-cisa-cm0053)

<a id="ref-debian-mdns"></a>Crawford, C. J. (2025, August 11). *Bug#1110883: release-notes: mDNS resolution in systemd-resolved disabled by default, breaking existing setups* [Mailing list post]. debian-doc. https://lists.debian.org/debian-doc/2025/08/msg00056.html
[Return to citation](#cite-debian-mdns)

<a id="ref-resolved-conf"></a>Debian. (n.d.). *resolved.conf(5)* [Manual page, systemd-resolved 262.2-1]. Debian Manpages. https://manpages.debian.org/testing/systemd-resolved/resolved.conf.d.5.en.html
[Return to citation](#cite-resolved-conf)

<a id="ref-debian-cloud-bug"></a>flaviovs. (2024, February). *Bug#1064235: cloud.debian.org: systemd-resolved et al. status (bookworm)* [Mailing list post]. debian-cloud. https://lists.debian.org/debian-cloud/2024/02/msg00029.html
[Return to citation](#cite-debian-cloud-bug)

<a id="ref-responder"></a>Gaffie, L. (n.d.). *Responder* [Computer software]. GitHub. https://github.com/lgandx/Responder
[Return to citation](#cite-responder)

<a id="ref-mitre-t1557"></a>MITRE. (2026, May 12). *Adversary-in-the-middle: Name resolution poisoning and SMB relay* (T1557.001, Version 2.0). MITRE ATT&CK. https://attack.mitre.org/techniques/T1557/001/
[Return to citation](#cite-mitre-t1557)

## Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1.0 | 2026-11-20 | First draft, written after the Incus container spike found LLMNR listening on the Debian 13 cloud image. |

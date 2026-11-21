# Spike: Incus Container Validation

**Purpose:** Determine empirically whether unprivileged Incus containers can satisfy RN-01 through RN-12, and identify which requirements need baseline review.

**Estimated time:** 20–30 minutes if everything works. Longer if nftables surprises you.

**Outcome:** A decision on whether the Incus backend supports containers, VMs, or both — recorded in the backend document's coverage table.

## Prerequisites

| Item | Version / Requirement |
|------|----------------------|
| Host OS | Debian 13 (Trixie) or Ubuntu 24.04+ |
| Incus | 6.x+ (check with `incus version`) |
| Network | `incusbr0` bridge exists and has DHCP enabled |
| Image | `images:debian/13/cloud` pulled locally |
| Bootstrap files | `shared/` directory present with the canonical files referenced by RN-03, RN-04, RN-05 |

Confirm the image is available:
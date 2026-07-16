# Bruno's own voice softswitch (FreeSWITCH + BYOC SIP trunk)

This is the "build our own" calling path. Instead of paying a CPaaS (Twilio,
SignalWire, Plivo, Vonage) to place each call over their HTTP API, we run
**FreeSWITCH** ourselves and bring our own carrier — a plain **SIP trunk** from any
wholesale voice provider. The Bruno backend originates calls into FreeSWITCH over
the Event Socket (ESL) and drives each call with **HTTAPI** (fetch-instructions
XML, the same idea as Twilio's TwiML).

**What this gets you:** full control of the dialplan, much lower per-minute cost at
volume, and no lock-in to any one provider's account (which is what bit us with
Twilio and Telnyx).

**What this does NOT fix by itself — read this:** whether your calls *ring* instead
of going to voicemail is decided by **STIR/SHAKEN attestation and caller
reputation**, which are set by the **SIP-trunk carrier** and the destination
carrier — not by our switch. A brand-new trunk number starts cold (attestation C)
and gets filtered to voicemail just like any new number. Running our own switch is
about control and cost. To make the number *ring* you still must:

1. Pick a trunk carrier that signs **A-level attestation** for numbers you own
   (Bandwidth and Telnyx do; ask any vendor before you sign up).
2. **Register the number** at <https://www.freecallerregistry.com> (covers Hiya,
   TNS, First Orion in one form) and set up branded caller ID / CNAM.
3. **Warm it**: start low-volume, allow longer talk-time, and stop the rapid
   7-second burst-dial pattern that spam engines flag.

---

## What you need

- A small **VPS with a public IP** (any provider; 1 vCPU / 1 GB is plenty to start).
  SIP + RTP need reachable ports, so a plain container host with host networking.
- A **SIP trunk** from a wholesale carrier. You'll get: a proxy/realm hostname,
  auth (username+password *or* IP auth), and at least one phone number (DID).
- Docker + Docker Compose on the VPS.

## Setup

1. **Copy this `deploy/softswitch/` folder to your VPS.**

2. **Configure your trunk.** Copy the example and fill in your carrier's details:
   ```bash
   cp freeswitch/conf/sip_profiles/external/bruno_trunk.xml.example \
      freeswitch/conf/sip_profiles/external/bruno_trunk.xml
   # edit username / password / realm / proxy (or register="false" for IP auth)
   ```
   Keep the gateway **name** as `bruno_trunk` (it must match `sip_gateway` in the app).

3. **Pick an ESL password** and start it:
   ```bash
   export ESL_PASSWORD="a-long-random-secret"
   docker compose up -d
   docker logs -f bruno-softswitch      # watch it boot and register the gateway
   ```
   Confirm the trunk registered:
   ```bash
   docker exec bruno-softswitch fs_cli -x "sofia status gateway bruno_trunk"
   # State should be REGED (or NOREG with UP for IP-auth trunks)
   ```

4. **Point the Bruno app at it.** In the app → **Setup → Self-hosted SIP softswitch**:

   | Field              | Value                                                    |
   |--------------------|----------------------------------------------------------|
   | `sip_esl_host`     | the VPS's **private** IP the backend can reach           |
   | `sip_esl_port`     | `8021`                                                   |
   | `sip_esl_password` | the `ESL_PASSWORD` from step 3                           |
   | `sip_gateway`      | `bruno_trunk`                                            |
   | `sip_from_number`  | your trunk DID in E.164, e.g. `+19786798009`            |
   | `voice_provider`   | `sip`                                                    |

   Also make sure `public_base_url` (where FreeSWITCH fetches call instructions) and
   `producer_callback` (your cell, for bridge calls) are already set.

5. **Test the link first.** On the softswitch card in Setup, click **Test connection**.
   It confirms the app can reach FreeSWITCH over ESL and that the `bruno_trunk` gateway
   is **registered** — so a wrong host/password or an unregistered trunk is caught here
   instead of a call silently failing. Green ✅ means you're ready.
6. **Place a call.** Use the **Call lead** button, or Setup's two-way test. The backend
   will `originate` through your trunk and hand the answered call to `/calls/sip/*`.

## Security notes

- **Never expose ESL (8021) to the public internet.** Keep FreeSWITCH and the
  backend on the same private network, or firewall 8021 to the backend's IP only.
  Anyone who reaches ESL with the password can place calls on your trunk.
- To let the backend connect from a *different* host on your private network, add
  its subnet to an ACL in `acl.conf.xml` and set `apply-inbound-acl` accordingly in
  `event_socket.conf.xml` (it defaults to loopback-only).
- The trunk password lives only in `bruno_trunk.xml` on your VPS — it is
  `.gitignore`d here so it never lands in the repo.

## How the call flow works

```
auto-dialer / Call button
        │  (ESL: bgapi originate … sofia/gateway/bruno_trunk/<lead>  &httapi{url=/calls/sip/amd})
        ▼
   FreeSWITCH  ──dials the lead through your SIP trunk──▶  the lead's phone
        │  (on answer, fetches HTTAPI instructions)
        ▼
  backend /calls/sip/amd  → returns: leave the recorded voicemail drop,
                             or (if auto_dial_transfer_enabled) bridge to your cell.
```

`bridge` and `record-vm` work the same way, on `/calls/sip/bridge` and
`/calls/sip/record-vm`.

## Notes / limitations

- **TTS (`speak`)** needs `mod_flite` in the FreeSWITCH image. If your image lacks
  it, the spoken lines are skipped but the call still bridges. The reliable path is
  to **record a voicemail greeting** (Setup → record voicemail) so the drop uses a
  hosted audio file (`playback`) instead of TTS.
- **Per-call answering-machine detection** isn't wired yet — the auto-dial path
  uses the same transfer-off-leaves-voicemail default as the other providers. Real
  AMD can be layered on later with `mod_avmd`.

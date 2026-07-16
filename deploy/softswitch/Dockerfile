# Bruno softswitch image = FreeSWITCH + the two optional modules the call flow uses:
#   • mod_flite — TTS, so the spoken consent line / fallback voicemail text works.
#   • mod_amd   — answering-machine detection, so a machine gets the recorded drop
#                 and only a live human is bridged to your cell.
#
# Both are OPTIONAL by design — if a package isn't available in your base image's
# apt repo, the build step is a no-op and the backend still works:
#   - no mod_flite → record a voicemail greeting (played via `playback`, no TTS), and
#   - no mod_amd   → calls fall back to the transfer-default behavior.
# So a missing package degrades gracefully; it never breaks calling.
FROM safarov/freeswitch:latest

RUN set -eux; \
    apt-get update || true; \
    # Install whichever of these the repo actually has; don't fail the build if a
    # package name differs on your base image.
    apt-get install -y --no-install-recommends \
        freeswitch-mod-flite freeswitch-mod-say-en freeswitch-mod-amd || true; \
    rm -rf /var/lib/apt/lists/*; \
    # Ensure both modules load at startup (append to the autoload list if present
    # and not already listed). Safe no-op if the file/module isn't there.
    MODS=/etc/freeswitch/autoload_configs/modules.conf.xml; \
    if [ -f "$MODS" ]; then \
        grep -q 'mod_flite' "$MODS" || sed -i 's#</modules>#  <load module="mod_flite"/>\n</modules>#' "$MODS"; \
        grep -q 'mod_amd'   "$MODS" || sed -i 's#</modules>#  <load module="mod_amd"/>\n</modules>#' "$MODS"; \
    fi

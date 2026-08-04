# Cutting the Google Cloud bill (~$1,000/mo → target well under $200)

The app runs on **Cloud Run** (backend + frontend) + **Cloud SQL** (Postgres).
The repo's deploy config is already lean; the big money is almost certainly
**Cloud SQL**. Do the steps in order — step 1 is usually 80% of the savings.

## Step 0 — See what you're actually paying for (2 min)
Google Cloud Console → **Billing → Reports**, group by **SKU / Service**. This
tells you which of Cloud SQL / Cloud Run / networking is the real driver so you
don't guess. Expect Cloud SQL to dominate.

## Step 1 — Right-size Cloud SQL (usually the whole problem)
A large or **High-Availability** Postgres tier can be $300–$800+/mo on its own.
For this workload a small shared-core instance is plenty.

```bash
# See the current tier + HA setting:
gcloud sql instances describe <INSTANCE> --format="value(settings.tier,settings.availabilityType,settings.dataDiskSizeGb)"

# Turn OFF High Availability if it's REGIONAL (this alone ~halves the DB cost):
gcloud sql instances patch <INSTANCE> --availability-type=ZONAL

# Downsize the machine to a small shared-core tier (fine for this app's load):
gcloud sql instances patch <INSTANCE> --tier=db-g1-small        # ~$25-35/mo
# (db-f1-micro is even cheaper for dev; db-g1-small is a safe prod-ish floor.)

# Cap the disk if it auto-grew large, and disable runaway auto-growth:
gcloud sql instances patch <INSTANCE> --no-storage-auto-increase
```
Patching restarts the DB briefly (a minute of downtime). Do it off-hours.

## Step 2 — Confirm the backend is the only always-on service
The backend MUST stay `--min-instances=1 --no-cpu-throttling` — the in-process
scheduler (auto emails/texts/calls, lead sourcing, follow-ups) only runs while an
instance is alive. That's ~$40-60/mo and is load-bearing; **do not** scale it to
zero. The **frontend already scales to zero** (no min-instances flag) — good.

Optional small trim (reversible, ~$15/mo): backend `--cpu=2` → `--cpu=1` in
`cloudbuild.backend.yaml`. Keep `--memory=2Gi` (1Gi OOM'd on boot) and keep
`--cpu-boost`. Only worth it after Step 1.

## Step 3 — Kill anything you're paying for twice
- `render.yaml` exists in the repo — if the app was ever deployed on **Render**
  too, cancel that; you only need Google.
- Delete old **Cloud Run revisions**, unused **Container/Artifact Registry**
  images, and any stopped/duplicate Cloud SQL instances.
- Cloud Build: the daily autonomous-improver + CI cost per-minute — negligible,
  but turn off the improver workflow if you're not using it.

## Step 4 — Verify
Re-check Billing → Reports after 24–48h. Target: Cloud SQL < ~$40, Cloud Run
< ~$70, everything else minimal → **well under $200/mo**.

> The single highest-leverage action is **Step 1** (downsize Cloud SQL + turn off
> HA). If you do nothing else, do that.

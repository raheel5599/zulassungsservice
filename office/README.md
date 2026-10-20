# TARIQ portals

Office `/`, dealer `/haendler`, driver `/fahrer` share one same-origin API. Production: https://zulassung.tariq-itconsulting.de. The transparent UG logo is used in all three portals.

## Connected workflow

1. An administrator creates dealer and driver invitations under Mitarbeiter / Händler. Links expire after 24 hours and are not sent automatically.
2. A dealer creates an order and optionally requests collection. Office sees it, reviews uploaded documents and assigns a collection or return to a driver.
3. The driver sees assigned orders and documents. Collection completion sets the shared order to Abgeholt. Return completion requires item selection, recipient name, signature and a task-bound uploaded photograph; it sets Ausgeliefert.
4. Document review, plate production, transport status and event history synchronize while the portal is visible (five-second polling). Conflicting writes are rejected with a refresh message.

## First setup

The API creates a random single-use code in its persistent data volume. Read it privately on the server:

```sh
cd /opt/tariq-zulassungsservice/office
docker compose -f compose.yml exec -T api cat /data/setup-code
```

Open the portal and enter the code, your name, a username and a password of at least 12 characters. The code is deleted after creating the administrator. Never put the code, invitation tokens or passwords in Actions logs. There are no shared default credentials. Existing browser sample data are not imported.

## Storage and access

Python 3.12 standard library + SQLite WAL and protected uploads in Docker volume `portal_data`. Back up the entire `/data` directory with the API stopped, or use SQLite's online backup API and a consistent upload backup. Do not run `docker compose down -v` on production. Application rebuilds retain the volume.

Passwords use salted PBKDF2-SHA256 (600,000 rounds). Sessions are revocable, expire after 12 hours and use Secure/HttpOnly/SameSite cookies. Mutation requests require the exact configured Origin. The API is reachable only on the internal Compose network; nginx proxies `/api`. Dealers see their orders; drivers see assigned transports and associated documents; Office sees all operations; only admins create accounts. Files have authenticated download routes, randomized disk names, type/size checks and no public bucket. Updates use optimistic versions. Personal preferences and unfinished drafts are isolated per user.

## Deliberately unfinished modules

Invoices/payment processing, outgoing chat/email, external registration/insurance APIs, vehicle assignment, route optimization and live tracking are not connected. Sample invoice and vehicle sections are labelled. Chat replies are private drafts, while order activity notifications are shared. Daily vehicle checks are personal records and are not an Office authorization mechanism. Account recovery, invitation renewal and disabling accounts still need administrator tooling before broader rollout.

## Local development and checks

Inside `office`: `npm ci`, `npm run build`, `python -m unittest discover -s api -v`.
Run the API with a private local data directory and development-only cookie settings:

```sh
DATA_DIR=/tmp/tariq-portal-dev PUBLIC_ORIGIN=http://localhost:5173 COOKIE_SECURE=0 python api/server.py
```

In another terminal run `npm run dev -- --host localhost`; Vite proxies `/api` to localhost:8000. Production always uses HTTPS and secure cookies. Do not use test passwords or fixtures in production.

Compose starts the API health check before nginx. GitHub Actions builds and tests the frontend and API; production deployment updates the existing Hetzner Compose project and Caddy configuration. Port 8091 is bound to loopback only.

## Zulassungsstelle, Termine und Wochenzähler

Office has a dedicated Zulassungsstelle section. Save an externally booked appointment (date/time, authority, booking reference, address, notes) even before orders exist; attach orders later. Create prepared hand-in lists in Händlerschalter mode and print a per-case hand-in manifest. These records are shared across Office accounts; dealers and drivers receive only their own order's visit summary.

The default 20 cases/week is a minimum, not a capacity. The counter separately shows reserved cases, actual submitted cases and the remaining minimum. A configurable optional weekly limit enables remaining-capacity tracking and is enforced atomically, including concurrent reservations. Cancelled records and regular appointments do not count toward the Händlerschalter minimum. Weeks run Monday–Sunday in the German operating calendar; delayed submissions count in their actual submission week. No upper limit is assumed if none has been entered.

Each authority has one active operating mode. Open plans prevent switching modes; appointments and Händlerschalter cases cannot be mixed in one authority's operating week. Confirm a change with the authority. Existing history is retained. Planning is not an external appointment booking or a guarantee of same-day processing.

The order workflow now distinguishes collection from customers, Office review, fully checked, authority submission, readiness for collection at the authority, return to Office and delivery to the customer. Submission requires fully checked assigned cases and reviewed uploads. Uploading new documents reopens a completed Office review. Recording readiness does not automatically complete a return delivery. Existing accounts, orders and documents are preserved by additive SQLite tables.

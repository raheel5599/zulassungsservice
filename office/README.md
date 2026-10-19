# TARIQ Office – Entwicklungsstand

Office-Dashboard (erste Demo) nach den Designvorlagen. Noch kein produktives Backend, keine Anmeldung und keine persistenten Daten. Bitte keine echten Ausweis- oder Kundendokumente eingeben.

## Lokal starten

```bash
cd office
npm install
npm run dev
```

## Docker / Hetzner

```bash
cd office
docker compose -f compose.yml up -d --build
```

Der Container ist nur über 127.0.0.1:8091 auf dem Server erreichbar. Für eine öffentliche Domain ist ein gesonderter HTTPS-Reverse-Proxy erforderlich, z. B. ein Caddy-Eintrag auf `127.0.0.1:8091`. **Nicht ohne Login und Schutzmaßnahmen öffentlich produktiv bereitstellen**.

## GitHub Actions

- `TARIQ Office - Build`: Build-Test bei Code-Änderungen.
- `TARIQ Office - Hetzner Deploy (manuell)`: nur nach manueller Freigabe.
- Benötigte Repository Secrets: `HETZNER_HOST`, `HETZNER_USER`, `HETZNER_SSH_KEY`, `HETZNER_KNOWN_HOSTS`.
- Der SSH-Benutzer braucht Docker-Rechte und Schreibrechte unter `/opt/tariq-zulassungsservice`. Kein Root-SSH erforderlich.
- Für `HETZNER_KNOWN_HOSTS` den SSH-Hostschlüssel **außerhalb des Workflows auf einem vertrauenswürdigen Weg verifizieren**, nicht blind aus ssh-keyscan übernehmen.

Das UG-Logo wird aus dem übergeordneten Repository übernommen.

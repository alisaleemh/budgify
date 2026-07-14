# Production deployment

Budgify runs on `alih-lxc-1` as part of the master Compose project in
`/opt/apps/docker-compose.yml`.

- GitHub Actions manages the source checkout at `/srv/budgify`.
- `budgify-web` and `budgify-sync` both build the `budgify:main` image from that checkout.
- The UI is published at `http://alih-lxc-1:8786/`.
- Persistent data, statements, configuration, password, and AI secrets remain under
  `/opt/apps/budgify` and are bind-mounted by the master Compose file.
- `/opt/apps/budgify` is a legacy checkout and must not be used as a build context.
- Do not start `/srv/budgify/docker-compose.yml`; `/srv/budgify` is a source checkout,
  not a second Compose runtime.

Host-specific operational instructions are maintained in `/opt/apps/AGENTS.md`.
Deployments run through `.github/workflows/deploy.yml` and `deploy.sh`.

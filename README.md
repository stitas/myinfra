# Personal VPS infrastructure

One Hetzner VPS (~8 GB RAM). Ansible provisions Ubuntu and K3s; Kubernetes runs
Traefik, Argo CD, cert-manager, Sealed Secrets, Headlamp, Umami and Copyparty.
PostgreSQL runs separately in Docker Compose. Application CI/CD and monitoring are planned.

## Setup and provisioning

- SSH aliases: `meka` as root, `meka-admin` as admin on the same host.
- Bootstrap installs `~/.ssh/meka_admin.pub` and passwordless sudo. Verify admin SSH
  before site provisioning disables root/password login.
- Configure the provider firewall below before provisioning.

Run Ansible commands from `ansible/`:

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml
```

Keep the Vault password at `~/.config/meka-secrets/ansible_vault_pass` (0600). Ansible reads it automatically through `ansible.cfg`.

Edit the existing encrypted Vault file:

```bash
ansible-vault edit group_vars/all/vault.yaml
```

The editor shows decrypted YAML. Saving and closing re-encrypts the file. Its required
contents look like this (replace placeholders with existing values):

```yaml
postgresql_superuser_password: "<existing postgres password>"
postgresql_passwords:
  umami: "<existing umami role password>"
backup_restic_password: "<existing Restic password>"
backup_b2_key_id: "<existing B2 key ID>"
backup_b2_application_key: "<existing B2 application key>"
```

Add a `postgresql_passwords` entry for each user in
`ansible/roles/postgresql/defaults/main.yml`. Values must match existing roles.

After configuring Vault, bootstrap and provision:

```bash
ansible-playbook -i bootstrap.ini playbooks/bootstrap.yml
```
```bash
ansible-playbook playbooks/site.yml
```

### Ansible execution order

`bootstrap.yml` connects through the root SSH alias in `bootstrap.ini`. It runs
these steps in order:

| Step | What it does |
| --- | --- |
| APT cache | Refreshes the Ubuntu package index. |
| Basic tools | Installs `git`, `curl`, `htop` and `unzip`. |
| Admin account | Creates `admin` in the `sudo` group. |
| SSH directory | Creates `/home/admin/.ssh` with owner-only access. |
| SSH public key | Copies the PC's `~/.ssh/meka_admin.pub` into the admin account's `authorized_keys`. |
| Passwordless sudo | Installs and validates the sudoers rule allowing `admin` to run commands as root. |

`site.yml` connects through the admin inventory and uses sudo. It runs these steps
in order:

| Step | What it does |
| --- | --- |
| SSH hardening | Disables root and password login, validates the SSH configuration and reloads SSH when changed. |
| Automatic APT updates | Installs `unattended-upgrades`, enables daily package-list refreshes and unattended upgrades, and disables automatic reboots. |
| Docker | Configures Docker's Ubuntu repository, installs Engine/Compose, limits container logs and starts Docker. |
| K3s | Installs the pinned version when needed, configures DNS, verifies the version, removes old installers and writes the external PostgreSQL EndpointSlice. |
| Pending DNS handlers | Applies queued K3s/CoreDNS restarts and waits for CoreDNS before continuing. Unchanged configuration queues no restart. |
| PostgreSQL | Starts the Compose container using Vault credentials, then creates application users and databases. |
| Copyparty directories | Creates UID/GID 10001 and the protected public, private and runtime-state directories. Argo CD deploys the application later. |
| Argo CD | Installs its Helm chart through K3s, waits for CRDs, creates missing projects and applies the root GitOps Application. |
| Backups | Installs pinned Restic, removes old archives, writes runtime credentials, initializes missing repositories and enables the backup timer. |

`infra_recovery_mode=true` option skips application database provisioning, Argo CD and
backups.

`recover.yml`  recovery sequence is described below.

### PostgreSQL operations


Ansible supplies `POSTGRES_PASSWORD` through a JSON Compose override on stdin, with
`no_log`. No new persistent password file is created, but Docker retains the decrypted
password in container environment metadata, accessible to root/Docker administrators.
Use Ansible for container creation/recreation. Plain `compose up` omits this override.
Restarts and unattended backups reuse the container without the PC's Vault password:

```bash
sudo docker compose -f /opt/postgresql/compose.yaml ps
sudo docker compose -f /opt/postgresql/compose.yaml exec postgres psql -U postgres
sudo docker compose -f /opt/postgresql/compose.yaml restart postgres
```

PostgreSQL 18 data lives in `/srv/postgresql/data/18/docker`

Compose and the Kubernetes EndpointSlice assume Docker gateway `172.17.0.1`

## Ownership and application updates

| Owner | Configuration |
| --- | --- |
| Ansible | SSH/users, Docker/K3s, PostgreSQL/container/roles, media directories, backups, external PostgreSQL EndpointSlice |
| K3s Helm controller | Argo CD installation |
| Argo CD | GitOps applications and AppProjects after Ansible creates missing projects; PostgreSQL's selectorless Service |
| Kubernetes controllers | Generated Secrets and certificates |

Edit application manifests under `kubernetes/` and publish through the normal
Git workflow. Argo CD follows remote `master`.

| Hostname | Service |
| --- | --- |
| [argocd.stitas.dev](https://argocd.stitas.dev) | Argo CD |
| [k3s.stitas.dev](https://k3s.stitas.dev) | Headlamp |
| [umami.stitas.dev](https://umami.stitas.dev) | Umami |
| [media.stitas.dev](https://media.stitas.dev) | Copyparty |

Ingresses use HTTPS `websecure`.Keep port 80 reachable for HTTP-01 certificate challenges.

Headlamp uses a shared cluster-admin account
behind Basic Auth and NetworkPolicy.

### Configuration revision counter

ConfigMap/Secret changes do not themselves change a Deployment's Pod template.
Increment the Deployment annotation after changing ConfigMap/SealedSecret:

```yaml
spec:
  template:
    metadata:
      annotations:
        infra.stitas.dev/config-revision: "2" # change "1" to "2"
```

This annotation has no numerical meaning. It is a manual Git-controlled
restart mechanism, not automatic configuration detection. An image change already
changes the Pod template.


## Backups

`backup.timer` runs at 03:00 VPS system time, with up to five minutes random delay. Both `/srv/backups/restic` and B2 receive:

- PostgreSQL roles and databases: `/var/lib/backup/staging/current/postgresql.sql`.
- All retained Sealed Secrets controller private keys: `sealed-secrets.json` in the
  same staging directory, selected by the key label in `kube-system`.
- Full `/srv/copyparty`, including uploaded public/private files and local `.hist` history.


Run backup manually using:
```bash
sudo systemctl start backup.service
sudo systemctl status backup.service backup.timer
sudo journalctl -u backup.service --since yesterday
```

## Recovery on a fresh replacement

Keep Vault, its password and the existing database/Restic/B2 credentials somewhere safe.
The selected B2 snapshot must contain the SQL dump, controller keys and media from
the current backup script. Check this before wiping the VPS. VPS local backup after wipe is lost.

Reinstall Ubuntu, configure the provider firewall and update SSH aliases. Bootstrap
admin SSH, then run recovery from the PC's `ansible/` directory:

```bash
ansible-playbook -i bootstrap.ini playbooks/bootstrap.yml
```

```bash
ansible-playbook playbooks/recover.yml
```

Recovery defaults to the latest B2 snapshot. To select a known-good snapshot:

```bash
ansible-playbook playbooks/recover.yml -e recovery_snapshot='<full snapshot ID>'
```

For a replacement inventory outside `ansible/`, add
`-i /path/to/replacement.ini -e @group_vars/all/vault.yaml` to the recovery command.
Verify admin SSH before recovery disables root/password login.

`recover.yml` connects through the admin inventory and uses sudo. It runs these
steps in order:

| Step | What it does |
| --- | --- |
| Base provisioning | Runs `site.yml` with recovery mode enabled: prepares K3s, PostgreSQL and media directories while skipping application database provisioning, Argo CD and backups. |
| Restic | Installs `bzip2` and pinned Restic, verifies its version and removes old archives without enabling scheduled backups. |
| B2 restore | Checks the repository, restores the selected snapshot and verifies restored files. Vault credentials are supplied through stdin to Restic's environment. |
| Sealed Secrets keys | Imports the backed-up controller private keys before the controller starts, allowing existing SealedSecret manifests to be decrypted later. |
| PostgreSQL data | Restores roles and databases from SQL, removing only the duplicate bootstrap `CREATE ROLE postgres;` statement. |
| Copyparty files | Restores public/private uploads and local `.hist` history, sets ownership and directory permissions, and leaves runtime state fresh. |
| Normal provisioning | Runs `site.yml` normally after successful restoration to configure application databases, Argo CD and backups. Argo CD syncs asynchronously. |

## Versions and maintenance

Ansible manages these settings in `/etc/apt/apt.conf.d/99-meka-updates`:

```text
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "false";
```

Unattended upgrades do not reboot the VPS. Reboot manually when required; package
updates can still restart individual services.

These are repository pins, not live installed versions. Changing a pin can update
installed software on provisioning/sync.
Docker/Compose packages follow the Docker APT repository; Traefik/CoreDNS follow K3s.
After installed-version verification succeeds, provisioning removes old K3s installers
and Restic archives from `/usr/local/src`, keeping the current version's artifact.

| Component | Repository version | Edit | Official versions | Notes |
| --- | --- | --- | --- | --- |
| K3s | `v1.35.9+k3s1` | `ansible/roles/k3s/defaults/main.yml` | [Releases](https://github.com/k3s-io/k3s/releases) | Bundled components follow K3s |
| Restic | `0.19.1` | `ansible/roles/backup/defaults/main.yml` | [Releases](https://github.com/restic/restic/releases) | Archive selected by CPU architecture |
| PostgreSQL | image `18.6` | `ansible/roles/postgresql/files/compose.yaml` | [Image](https://hub.docker.com/_/postgres) | Major changes need data migration |
| Argo CD | chart `10.11.6` (app `3.5.6`) | `ansible/roles/argocd/tasks/main.yml` | [Charts](https://github.com/argoproj/argo-helm/releases) | Edit chart version; check appVersion |
| cert-manager | chart `v1.21.3` | `kubernetes/gitops/infrastructure/cert-manager/cert-manager.yaml` | [Releases](https://github.com/cert-manager/cert-manager/releases) | Includes controller and CRDs |
| Headlamp | chart `0.46.0` (app `0.46.0`) | `kubernetes/gitops/infrastructure/headlamp/headlamp.yaml` | [Releases](https://github.com/kubernetes-sigs/headlamp/releases) | Select Helm chart release |
| Sealed Secrets | chart `2.20.0` (app `0.40.0`) | `kubernetes/gitops/infrastructure/sealed-secrets/sealed-secrets.yaml` | [Releases](https://github.com/bitnami-labs/sealed-secrets/releases) | Chart differs from controller; retain keys |
| Umami | image `3.4.1` | `kubernetes/resources/umami/deployment.yaml` | [Releases](https://github.com/umami-software/umami/releases) | Startup migrates databases |
| Copyparty | image `1.20.26` | `kubernetes/resources/copyparty/deployment.yaml` | [Releases](https://github.com/9001/copyparty/releases) | Preserve access rules and media paths |
| PostgreSQL Ansible collection | `4.2.0` | `ansible/requirements.yml` | [Releases](https://github.com/ansible-collections/community.postgresql/releases) | Reinstall requirements on PC |

Update the packages in the VPS:
```bash
sudo apt update
```
```bash
sudo apt upgrade
```
```bash
sudo apt autoremove
```

Record in the relevant Git change:

- [ ] Review date, components, current/selected versions (or unchanged).
- [ ] Edit pins and this table; run local checks.
- [ ] After upgrading, record completion date, component and actual installed version.

## Provider firewall

Hetzner Cloud's firewall is configured manually, outside Ansible. Apply equivalent
rules at another provider:

| Traffic | Allow |
| --- | --- |
| TCP 80/443 | Public; HTTP-01 needs port 80 |
| TCP 22 | Trusted management addresses |

## Local validation

Run from the repository root:

```bash
python3 scripts/validate.py
```

Requires Python 3, PyYAML, Jinja2 and Bash. It checks:

- YAML syntax and duplicate keys in `.yaml`/`.yml` files, excluding `.git` and encrypted Vault files.
- Source directories for Argo Applications referencing this repository.
- Bash syntax after rendering the backup template with role defaults.

It checks local files and does not deploy anything; it does not validate Kubernetes
schemas or live behaviour.

Other local checks:

```bash
docker compose -f ansible/roles/postgresql/files/compose.yaml config --quiet
cd ansible
ansible-playbook --syntax-check playbooks/bootstrap.yml
ansible-playbook --syntax-check playbooks/site.yml
ansible-playbook --syntax-check playbooks/site.yml -e infra_recovery_mode=true
ansible-playbook --syntax-check playbooks/recover.yml
```

# Agent guide

This file is the contributor guide for the whole repository. Read it before changing
infrastructure code. `README.md` is the owner's operator guide; the manifests and
playbooks are the source of truth for implementation details.

## Working agreement

- **Do not modify `README.md` unless the user explicitly requests README changes.**
  The owner has edited its content and layout deliberately. Report documentation
  drift instead of silently rewriting it. Keep contributor context here; do not
  create a separate `docs/` directory.
- Read the current files, not just `git HEAD`. The working tree can contain substantial
  owner changes and required untracked files. Preserve them, especially the encrypted
  Vault file. Do not reset, clean, re-encrypt or replace unrelated work.
- Repository edits and local validation do not authorize production access or changes.
  Do not SSH to the VPS, run provisioning/recovery, apply manifests, start backups,
  prune repositories, rotate credentials, change DNS/firewalls or push changes unless
  those actions are within the user's explicit request.
- Prefer small, direct Ansible tasks, Bash and plain Kubernetes YAML. This is one
  person's infrastructure, not a platform for a team. Avoid adding services,
  controllers, frameworks or abstraction layers for minor convenience.
- Never print secret values, decrypt Vault to the terminal, dump Kubernetes Secrets,
  inspect container environments into output, or put secrets in Git, command arguments
  or annotations. Use placeholders in examples and `no_log` on sensitive tasks.
- State what was checked locally and what remains unverified on the VPS. Configuration
  in Git does not prove a live firewall, DNS record, controller or backup is working.

### Deliberate decisions to preserve

These are intentional choices, not missing features to add back during cleanup:

- The test suite was removed at the owner's request. Do not recreate `tests/`, test
  frameworks or historical test commands unless requested.
- No repository-managed download checksum verification for K3s or Restic. Keep explicit
  version pins, installed-version comparisons and post-install version verification.
- No upgrade opt-in flags, downgrade/skipped-minor restrictions or version-change
  approval mechanisms. Applying a changed pin can update installed software.
- No recovery marker, recovery lock, confirmation flag or existing-installation-path
  assertions. Recovery targets a fresh installation by procedure, not an enforced lock.
- No persistent PostgreSQL password files. Vault supplies the configured passwords.
- No Restic password comparison/guard machinery. Deploy the existing Vault password
  directly; that does not rotate a repository's encryption keys.
- No online SQLite snapshot helper or restore overlay. Copyparty's runtime databases
  are disposable; uploaded documents and document history are not.
- No configuration reloader controller or elaborate configuration hashing. Applications
  use a manual Pod-template revision annotation.
- Automatic Ubuntu updates are enabled; automatic reboots are explicitly disabled.
- Application CI/CD and monitoring/alerts are planned. Their absence alone is not a
  defect, and does not authorize introducing them.

## Architecture and navigation

Target: one Hetzner VPS with approximately 8 GB RAM, Ubuntu 26.04.1 LTS, amd64 or
arm64. Host directories are local storage, not replicated storage. Keep resource
requests and additional background services appropriate for this single machine.

K3s runs Traefik, Argo CD, cert-manager, Sealed Secrets, Headlamp, Umami and Copyparty.
PostgreSQL runs outside Kubernetes in Docker Compose. Backups use Restic against a
local repository and Backblaze B2 through its S3 API.

| Area | Start here |
| --- | --- |
| Operator commands and current version table | `README.md` — read, do not edit without authorization |
| SSH inventory, role paths and Vault password location | `ansible/ansible.cfg`, `ansible/inventory.ini`, `ansible/bootstrap.ini` |
| Initial admin account | `ansible/playbooks/bootstrap.yml`, `ansible/roles/common/tasks/main.yml`, `ansible/roles/security/tasks/main.yml` |
| Normal provisioning and ordering | `ansible/playbooks/site.yml` |
| Automated data recovery | `ansible/playbooks/recover.yml` |
| SSH and automatic APT updates | `ansible/roles/security/tasks/ssh.yml`, `ansible/roles/security/tasks/updates.yml` |
| Docker packages and daemon logging | `ansible/roles/docker/tasks/main.yml` |
| K3s installation, DNS and endpoint | `ansible/roles/k3s/` |
| PostgreSQL configuration and identities | `ansible/roles/postgresql/` |
| Media host directories and UID/GID | `ansible/roles/copyparty/tasks/main.yml` |
| Backup contents, retention and scheduling | `ansible/roles/backup/defaults/main.yml`, `tasks/main.yml`, `templates/backup.sh.j2` |
| Restic binary installation and archive cleanup | `ansible/roles/backup/tasks/restic.yml` |
| Argo CD installation/bootstrap | `ansible/roles/argocd/tasks/main.yml` |
| Root GitOps Application | `kubernetes/bootstrap/gitops-manager.yaml` |
| Projects, child Applications and Helm chart values | `kubernetes/gitops/` |
| Actual application/infrastructure resources | `kubernetes/resources/` |

## Ownership boundaries and GitOps

| Owner | Responsibility |
| --- | --- |
| Ansible | Host packages/users/SSH, Docker, K3s, PostgreSQL Compose and database identities, media directories, backup jobs, external PostgreSQL EndpointSlice |
| K3s manifest/Helm controllers | Resources in the server manifests directory; installation of Argo CD from its `HelmChart` |
| Argo CD | Child Applications, chart releases and resources under their configured Git paths; AppProjects after initial bootstrap |
| Sealed Secrets controller | Ordinary Secrets generated from committed SealedSecrets |
| cert-manager | ACME issuance/renewal and generated TLS Secrets |
| Operator | Provider firewall, SSH aliases, DNS, off-server recovery credentials and authorized production operations |

The reconciliation chain is:

```text
site.yml -> K3s HelmChart for Argo CD -> gitops-manager
          -> kubernetes/gitops (recursive) -> child Applications
          -> Helm charts or kubernetes/resources/<component>
```

- The Git repository source is `https://github.com/stitas/myinfra.git`; Applications
  follow remote `master`. Local changes do not deploy. Publication to that branch can
  trigger automated synchronization, pruning and self-healing.
- Argo CD's own chart configuration is embedded in the Ansible role, not managed by
  another Argo Helm Application. `argocd-resources` manages ancillary resources such
  as its sealed GitHub webhook secret.
- Ansible creates only missing AppProjects, then applies the root Application. Do not
  change it to overwrite existing projects on every run: Argo CD manages their policy
  from `kubernetes/gitops/projects.yaml`.
- The `infrastructure` project has broad cluster permissions. The `applications`
  project targets `app-*` namespaces and permits Namespace resources. Understand the
  installed AppProject schema before relying on finer restrictions or changing access.
- Most raw-resource Applications have bounded dependency retries: 20 attempts, an
  initial 10-second backoff, factor 2, capped at one minute. They help CRDs/controllers
  become available; they are not a guarantee that all applications are ready when
  Ansible finishes. Preserve useful waits without adding a dependency framework.
- `headlamp-resources.yaml` has an explicit `directory.include` list. Adding a file
  under `kubernetes/resources/headlamp/` alone will not make it reconcile; update the
  include list when a new resource is intended to be deployed.

## Ansible execution and host assumptions

Run Ansible from `ansible/`. The config uses relative inventory and role paths.
`inventory.ini` targets the SSH alias `meka-admin`; `bootstrap.ini` targets `meka`.
Both use group `vps`. SSH host addresses, users and private keys are supplied through
the operator's SSH configuration, not hardcoded into these inventories.

Ubuntu 26.04 uses Python 3.14. Use ansible-core 2.20 or newer with compatible controller
Python; the 2.20/2.21 releases support controller Python 3.12–3.14. Do not assume a
workspace's system Ansible supports the VPS just because local syntax checks pass.
`ansible/requirements.yml` pins the PostgreSQL collection; install it on the controller
when needed. Verify version-dependent behavior using official documentation for the
configured release, not whichever documentation happens to be latest.

### The three entry points

- `bootstrap.yml`: refreshes APT, installs basic tools, creates `admin`, installs
  `~/.ssh/meka_admin.pub`, and grants passwordless sudo. It does not harden SSH yet.
- `site.yml`: SSH hardening -> automatic APT settings -> Docker -> K3s -> pending DNS
  handlers -> PostgreSQL -> media directories -> Argo CD -> backups. Plays use become.
- `recover.yml`: imports site provisioning in recovery mode, restores a B2 snapshot,
  then imports ordinary site provisioning. It does not bootstrap admin SSH itself.

`infra_recovery_mode` defaults to false in `site.yml`. True skips application database
provisioning, Argo CD and the full backup role. It still starts PostgreSQL, configures
K3s and creates media directories; required PostgreSQL Vault variables are still
checked. It does not stop an already running cluster, application or backup timer.

Let `recover.yml` manage its own per-play mode. Passing
`-e infra_recovery_mode=true` to the entire recovery invocation would also override
the final normal site run and prevent application/backup provisioning.

### Ordering, idempotence and maintenance details

- The two K3s DNS tasks manage different files and deliberately notify the same
  restart/wait handlers. Pending notifications are deduplicated. `flush_handlers`
  in `site.yml` applies them before dependent roles; notification alone would defer
  them until the end of the main task section. The flush runs all pending handlers.
- CoreDNS restart has 12 retries with five-second delays; rollout readiness has a
  120-second timeout. Argo CRD bootstrap has 60 retries, five-second delays and a
  ten-second command timeout. Do not replace these with unbounded waits.
- Ansible `block` groups tasks, can share directives, and supports `rescue`/`always`;
  it is not a transaction. Cleanup blocks must remain after successful version
  verification. Registered results are used by the following cleanup tasks.
- K3s, kubeseal and Restic compare installed versions to pins. Same-version runs skip
  installing; changed pins drive installation, including an older configured version. Never run
  normal provisioning merely as a validation command.
- Cleanup only searches regular files directly under `/usr/local/src`. It preserves
  `install-k3s-<configured-version>.sh`, `kubeseal-<version>-linux-<arch>.tar.gz` and
  `restic-<version>-<arch>.bz2`; it removes older matching files and the legacy
  `install-k3s.sh` after verification succeeds.
  It does not manage arbitrary installer files or fetch a missing retained artifact
  when installation is otherwise skipped.
- The K3s role installs the pinned kubeseal CLI through `tasks/kubeseal.yml` for
  amd64/arm64. It verifies a temporary executable before replacing
  `/usr/local/bin/kubeseal`; no versioned executable copies are retained. Cleanup
  removes old archives only after the installed version is verified. The CLI does
  not install or upgrade the Sealed Secrets controller.
- Docker uses the detected Ubuntu codename (`resolute` on 26.04), installs dependencies
  for `deb822_repository`, and uses Docker's upstream APT repository. No hardcoded
  Noble suite or third-party Ubuntu derivative support should be introduced.
- Docker daemon logging is bounded using the `local` driver. A changed daemon config
  restarts Docker; this can affect PostgreSQL availability.
- K3s `config.yaml` and Docker `daemon.json` are fully managed file contents, not
  merges with manual live edits. Add intended settings at their Ansible source or a
  deliberately chosen supported configuration boundary so reruns preserve them.
- `/etc/apt/apt.conf.d/99-meka-updates` manages daily package-list refreshes and
  unattended upgrades, plus `Unattended-Upgrade::Automatic-Reboot "false"`.
  The role ensures `unattended-upgrades` exists. It does not add Docker's repository
  to unattended-upgrade allowed origins. General APT upgrades and kernel reboots are
  separate maintenance operations; package updates may restart services.
  The periodic value `"1"` means once per day, not 01:00; APT's systemd timers control
  when those daily jobs run.

## Secrets and their sources

The encrypted file is `ansible/group_vars/all/vault.yaml`. Its decryption password
is read from `~/.config/meka-secrets/ansible_vault_pass`, outside Git. Do not read or
change its values unless the requested task requires it; never include them in
output. With an external inventory, callers may need
`-e @group_vars/all/vault.yaml` from `ansible/` so these variables are loaded.

| Vault variable | Used for |
| --- | --- |
| `postgresql_superuser_password` | Initial PostgreSQL container environment and Ansible database administration |
| `postgresql_passwords` | Mapping keyed by database **user**, currently including `umami` |
| `backup_restic_password` | Unlocks Restic repository keys for unattended jobs and recovery |
| `backup_b2_key_id` | B2 S3 access key ID (`AWS_ACCESS_KEY_ID`) |
| `backup_b2_application_key` | B2 S3 secret key (`AWS_SECRET_ACCESS_KEY`) |

Vault encryption and Kubernetes sealing are different systems. Updating a Vault
variable does not update a committed SealedSecret. Preserve existing database and
Restic passwords unless rotation is explicitly requested and coordinated.

| SealedSecret | Namespace | Encrypted fields |
| --- | --- | --- |
| `argocd-secret` | `argocd` | `webhook.github.secret` |
| `umami-secrets` | `app-umami` | `APP_SECRET`, `DATABASE_URL` |
| `copyparty-accounts` | `app-copyparty` | `accounts.conf` |
| `headlamp-basic-auth` | `headlamp` | `users` |

- Inspect metadata and encrypted field names when learning these files; dumping
  ciphertext or decrypted values adds no useful context. Names/namespaces matter to
  the default sealing scope; renaming resources may require resealing.
- The controller is named `sealed-secrets-controller` in `kube-system`, set by the
  Helm chart's `fullnameOverride`. Use matching `kubeseal` controller-name/namespace
  options when needed. Fetching a live certificate is cluster access; offline
  recovery unsealing produces plaintext and must write only to protected destinations.
- Argo CD's chart marks its generated Secret with
  `sealedsecrets.bitnami.com/patch: "true"`. Preserve the arrangement that lets the
  webhook value coexist with chart-managed Secret fields.
- `no_log` suppresses Ansible task output; it is not encryption and does not remove
  plaintext from process memory, Docker metadata or generated files.
- Secret-bearing `environment:` values can appear in Ansible's remote shell command.
  Recovery passes JSON over stdin to a short Python process which supplies Restic's
  environment. Do not simplify it into secret command arguments. B2 credentials
  ultimately exist in Restic's environment and remain accessible to privileged users.
- Daily jobs deliberately use root-only `/etc/backup/restic-password` and `b2.env`.
  The PC/Vault password is unavailable during unattended jobs. Do not remove these
  files when simplifying recovery or PostgreSQL credential handling.

## PostgreSQL: data, networking and password behavior

Source files are under `ansible/roles/postgresql/`. The host Compose file is
`/opt/postgresql/compose.yaml`, project name `postgresql`, service name `postgres`.
Avoid relying on a generated container name.

- Mount: `/srv/postgresql/data` -> `/var/lib/postgresql`; the PostgreSQL 18 image uses
  `18/docker` beneath it. Preserve the full parent volume. A major image change needs
  a data migration, not just a pin edit or a changed host mount.
- PostgreSQL binds to `127.0.0.1:5432` for host/SSH-tunnel access and
  `172.17.0.1:5432` for Kubernetes. It is not intentionally published on all interfaces.
- Ansible writes `ansible/roles/k3s/files/postgresql-endpoint.yaml` into
  `/var/lib/rancher/k3s/server/manifests/`. It creates namespace `database` and an
  EndpointSlice named `postgresql`, labelled for the Service, pointing at `172.17.0.1`.
- Argo CD owns the selectorless Service at
  `kubernetes/resources/postgresql/service.yaml`. Cluster clients use
  `postgresql.database.svc.cluster.local:5432`. Do not add a Pod selector or move
  endpoint ownership to a second manager.
- A Docker bridge address change requires coordinated updates to Compose and the
  EndpointSlice. Check the actual bridge only when live inspection is authorized.

The Compose file contains no administrator password. Ansible supplies
`POSTGRES_PASSWORD` through a JSON override on stdin during `compose up`, using
`no_log`. The `replace('$', '$$')` is important: it prevents Compose interpolation
from changing password characters. Docker retains the result in container environment
metadata. Existing PostgreSQL data is not reinitialized when that environment changes;
editing the superuser Vault variable alone does not rotate the database role password.

Use the Ansible role to create/recreate this container. Ordinary `compose up` with
only the public file omits the credential override. `compose ps`, `exec` and `restart`
use the existing container without accessing Vault. Backups use `exec -T postgres
pg_dumpall -U postgres`; they do not need PostgreSQL password files.

Application identities come from `postgresql_databases` in the role defaults, with
`postgresql_passwords[item.user]`. Database administration connects to localhost using
the Vault superuser password and the apt-installed `python3-psycopg2` driver. A changed
application password can update the role; coordinate its sealed connection URL.
Percent-encode URL credentials when constructing a `DATABASE_URL`; shell quoting is
not URL encoding. Keep decrypted URLs out of output.

## Workload contracts and access control

| Component | Namespace | Hostname | Important contract |
| --- | --- | --- | --- |
| Argo CD | `argocd` | `argocd.stitas.dev` | TLS at Traefik; internal Argo server uses insecure HTTP intentionally |
| Headlamp | `headlamp` | `k3s.stitas.dev` | Basic Auth plus a protected proxy path to a shared cluster-admin service account |
| Umami | `app-umami` | `umami.stitas.dev` | Environment from `umami-secrets`; PostgreSQL is external to Kubernetes |
| Copyparty | `app-copyparty` | `media.stitas.dev` | Owner-only writes; public direct links; authenticated private volume |

All configured application ingresses use Traefik's `websecure` entrypoint and the
`letsencrypt` ClusterIssuer. Keep Umami's explicit entrypoint annotation. cert-manager
uses HTTP-01 on ingress class `traefik`; port 80 must remain reachable for issuance
and renewal even though application traffic uses HTTPS. Its chart also specifies
public resolvers for challenge self-checks. No extra redirect framework is required.

### Copyparty

- Fixed UID/GID `10001` must agree across the Ansible service user, Pod security
  context, host directory ownership and recovery. Top-level storage directories are
  `0700`; the container runs non-root, drops capabilities and disallows escalation.
- HostPath directories must already exist. Mounts are `/srv/copyparty/public` ->
  `/w/public`, `/srv/copyparty/private` -> `/w/private`, and `state` -> `/cfg`.
  These are local directories, not PVCs provisioned by a storage controller.
- Public volume `/` has `g: *`: anonymous users may retrieve direct URLs without
  anonymous directory browsing. Only `admin` has `rwmda` write/move/delete access.
  `/private` grants access only to `admin`. Do not replace `g` with anonymous `r` or
  loosen writes as a troubleshooting shortcut.
- ConfigMap `copyparty-config` supplies `copyparty.conf`; Secret `copyparty-accounts`
  supplies `accounts.conf`. Both mount via `subPath` into `/cfg`.
- `hist: /cfg/hists/` places runtime indexes/caches under the state mount. Uploaded
  document history using the current local `.hist` behavior is separate. Do not
  assume all files named history are disposable or all SQLite files are consistent.
  If changing history mode/location, check the pinned Copyparty documentation and
  update both backup and recovery coverage.
- `xff-src: 10.42.0.0/16`, `xff-hdr: x-forwarded-for`, and `rproxy: -1` depend on the
  current proxy path and K3s Pod CIDR. Revisit together when changing networking;
  do not trust arbitrary public client-supplied forwarded headers.

### Pod replacement and probes

Copyparty and Umami are single-replica Deployments with `Recreate` strategy, so updates
have brief downtime. Their manual restart annotation is
`spec.template.metadata.annotations.infra.stitas.dev/config-revision`.

Increment the annotation string, for example `"1"` -> `"2"`, with Copyparty ConfigMap
or accounts Secret changes and Umami environment Secret changes. `subPath` mounts do
not refresh in an existing Pod; environment values are read at process startup.
An image edit already changes the Pod template and needs no separate counter bump.
This is not automatic configuration detection. Never put secret values or their
derived sensitive content into annotations.

Copyparty's probes are TCP checks on its named HTTP port; Umami checks
`/api/heartbeat`. Both allow roughly five minutes for startup. PostgreSQL's
`pg_isready` tests server availability, not application-password correctness. These
checks do not prove media authorization, preserved analytics or end-to-end recovery.

### Headlamp

- The chart enables `unsafeUseServiceAccountToken` and proxy auth, disables creation
  of its chart ClusterRoleBinding, and uses ServiceAccount `headlamp`. The separate
  `rbac.yaml` grants that account `cluster-admin`. Do not describe users as having
  separate least-privilege Kubernetes identities.
- The chart's own ingress is disabled. The resource ingress attaches identity-header
  stripping **before** Basic Auth. Basic Auth creates `X-Forwarded-User` and removes
  the Authorization header. Preserve middleware order and strip rules.
- NetworkPolicy allows TCP 4466 only from Pods labelled Traefik in `kube-system`.
  Its namespace and Pod selectors are in the same peer, giving AND semantics.
  Splitting them into separate peers would broaden access. Chart upgrades can change
  labels, ports and service names; check these references together.
- Whether NetworkPolicy is actually enforced and whether a proxy can be bypassed
  require authorized live verification. Keep the Service ClusterIP; do not expose an
  alternate unauthenticated route to this shared administrative account.

## Backup contract

Read `templates/backup.sh.j2` before changing backup or recovery paths. Host entry
point: `/usr/local/sbin/backup`, run by root through `backup.service`.

| Data | Source included in each enabled repository |
| --- | --- |
| All PostgreSQL databases and roles | `/var/lib/backup/staging/current/postgresql.sql`, produced with `pg_dumpall` |
| All retained labelled sealing-key Secrets | `/var/lib/backup/staging/current/sealed-secrets.json`, exported from `kube-system` |
| Media and document history | Full configured `backup_media_path`, normally `/srv/copyparty`, when enabled |

Preserve these behaviors:

1. `umask 077`, protected staging and a nonblocking exclusive `flock` on
   `/run/lock/backup.lock`. Acquire the lock before clearing `staging/current`, so an
   overlapping run cannot delete an active run's plaintext. The lock file existing
   is not evidence of an active lock; the kernel releases the lock with its handles.
2. Keep stable source paths so Restic's path-based snapshot/retention grouping stays
   consistent. Exit and signal traps remove plaintext; a later locked run removes
   leftovers after SIGKILL/power loss. Do not claim secure erasure or cleanup after
   every possible interruption.
3. Export **all** Secrets selected by the presence of
   `sealedsecrets.bitnami.com/sealed-secrets-key`. Do not retain only the latest key
   or filter away old keys needed by existing ciphertext.
4. Use the existing small export sanity check: a nonempty list of Secrets, expected
   metadata and nonempty `tls.key`/`tls.crt` fields. Metadata cleanup retains portable
   names/namespaces/labels/annotations and strips the client last-applied annotation.
   It is not cryptographic private-key/certificate validation.
5. Export failure, malformed/empty keys, failed/empty SQL dump, or a missing enabled
   media source stops before updating repositories or applying retention.
6. Once sources are valid, attempt local and enabled B2 backups even if local backup
   fails. Apply retention only after that destination's successful backup. Report a
   failure if any destination or its prune fails; do not let the last success hide it.

The local repository is `/srv/backups/restic`; B2 is configured by
`backup_b2_repository` using an `s3:https://...` URL. The B2 API key and Restic password
serve different purposes: storage authorization versus unlocking encryption keys.
Do not replace the S3 credential names with B2-native backend variables without
changing the backend deliberately.

Provisioning checks remote repository configuration before initializing it. Only
Restic's missing-repository return code `10` triggers remote initialization; other
errors must fail. Do not turn authentication/network errors into an unconditional
`restic init` or assume a changed password means the repository does not exist.

Retention keeps 5 daily, 2 weekly and 1 monthly snapshots, plus `recovery-hold` tags;
the sets overlap. These values live in defaults, not in an external scheduler. The
timer runs at 03:00 VPS system time with up to five minutes random delay and
`Persistent=true`. The service has a six-hour timeout and starts after network,
Docker and K3s units; ordering alone does not prove those workloads are healthy.

The job does not back up the K3s datastore or raw PostgreSQL volume. Copied live
Copyparty SQLite databases are not guaranteed consistent. Sessions, shares, upload
metadata and caches may be lost/rebuilt under simplified recovery, while public/private
uploads and local `.hist` document revisions must be preserved. Local storage does
not survive losing/resetting the VPS. Keep unlock credentials and a private-key
fallback independently off-server; a public sealing certificate cannot decrypt secrets.

## Recovery contract

`recover.yml` is a state-changing fresh-VPS restore, not a local check or repeatable
SQL merge. Required operator inputs are the original Vault values, working admin SSH,
provider firewall/DNS setup and a B2 snapshot with the current SQL/key/media layout.
It defaults to `recovery_snapshot: latest`; a full known-good ID can be supplied.

The implemented sequence is:

1. Import `site.yml` with recovery mode true so applications and scheduled backups
   are not provisioned before their data exists.
2. Install `bzip2` and reuse only the backup role's `restic` tasks, without running
   its repository initialization, credential deployment or timer setup.
3. Create a root-only temporary directory under `/root`. Pass Vault credentials as
   JSON on stdin to Python; remove inherited Restic password-file/password-command
   settings and supply the credentials in the child Restic process environment.
4. Run `restic check`, then restore the selected snapshot with `--verify` into `data/`
   below the temporary directory. Allow disk space for this tree and the final data.
5. Apply backed-up sealing-key Secrets server-side with field manager
   `myinfra-recovery`, before installing the controller. Server-side apply avoids
   duplicating private keys in a client last-applied annotation.
6. Pipe SQL through `sed` to remove only `CREATE ROLE postgres;`, retaining its
   `ALTER ROLE`, then into container `psql -X --set ON_ERROR_STOP=on`. Preserve Bash
   `pipefail` and Compose `exec -T`. Restoring SQL can change role passwords; Vault and
   sealed application credentials must match the restored values.
7. Copy `public/.` and `private/.` with `cp -a`, including hidden document history;
   restore ownership and directory permissions. Leave the fresh runtime state in place.
8. Remove the temporary tree in `always`, including on ordinary task failure. A failed
   host does not proceed to final normal provisioning. An interruption that prevents
   Ansible cleanup can leave protected plaintext behind.
9. Import normal site provisioning to configure database identities, Argo CD and
   backups. Argo CD then recreates Kubernetes resources from remote `master` and loads
   the original encrypted manifests through the restored keys.

Do not infer safeguards that are absent: recovery mode neither suspends existing
services/timers nor rejects an existing installation. A partial SQL restore is not
rolled back; retry on a clean target. SQL/media are not one atomic point-in-time
snapshot. A snapshot predating a needed sealing key cannot decrypt newer ciphertext.
If a controller has already started, it must reload imported keys before relying on
them. Restoring only Git or a public sealing PEM is insufficient.

Changing staging paths, media paths, key namespaces or snapshot contents requires
checking **both** backup production and recovery consumption. Do not change one side
alone. Do not create another persistent PostgreSQL password file, credential-cache
service or recovery interlock to make restoration work.

## Version changes and coupled edits

Read current pins from these files; do not assume this guide or an operator's report
is the live installed version. Chart versions and application versions are different.

| Component | Source of the pin / related edits |
| --- | --- |
| K3s | `ansible/roles/k3s/defaults/main.yml`; bundled Traefik/CoreDNS follow it |
| kubeseal CLI | `kubeseal_version` in `ansible/roles/k3s/defaults/main.yml`; independent of the controller chart pin |
| Restic | `ansible/roles/backup/defaults/main.yml`; binary installation is in `tasks/restic.yml` |
| PostgreSQL | `ansible/roles/postgresql/files/compose.yaml`; major upgrades also affect the data-layout/recovery plan |
| Argo CD | HelmChart embedded in `ansible/roles/argocd/tasks/main.yml` |
| cert-manager | `kubernetes/gitops/infrastructure/cert-manager/cert-manager.yaml`; review chart CRD values |
| Headlamp | `kubernetes/gitops/infrastructure/headlamp/headlamp.yaml`; review ingress, RBAC, middleware, labels and NetworkPolicy port |
| Sealed Secrets | `kubernetes/gitops/infrastructure/sealed-secrets/sealed-secrets.yaml`; retain key namespace/controller name and recovery compatibility |
| Umami | `kubernetes/resources/umami/deployment.yaml`; startup may apply database migrations |
| Copyparty | `kubernetes/resources/copyparty/deployment.yaml`; check permission syntax, proxy trust and history behavior |
| PostgreSQL collection | `ansible/requirements.yml`; the controller must have the requested collection installed |

Docker/Compose/containerd packages are not pinned and can change through APT maintenance.
K3s's own container runtime is separate from the Docker runtime running PostgreSQL.
Do not assume an APT upgrade updates pinned images, Helm charts, K3s or the managed
Restic binary. Do not silently perform a live upgrade to validate a pin edit.

## Local validation without deployment

From the repository root:

```bash
docker compose -f ansible/roles/postgresql/files/compose.yaml config --quiet
git diff --check
```

From `ansible/`, using a compatible ansible-core:

```bash
ansible-playbook --syntax-check playbooks/bootstrap.yml
ansible-playbook --syntax-check playbooks/site.yml
ansible-playbook --syntax-check playbooks/site.yml -e infra_recovery_mode=true
ansible-playbook --syntax-check playbooks/recover.yml
```

`--list-tasks` can help inspect ordering locally. Do not replace these checks with a
normal playbook run. `--check` is not a blanket guarantee of no side effects for
arbitrary future task changes. Validate live behavior only within the authorized scope.

Compose `config --quiet` validates the public file, not its secret override or
database connectivity. Syntax checks do not prove the remote tasks will succeed.

There is no test suite or CI workflow to invoke. Do not rely on historical test files,
optional test environment variables, `/tmp` environments from another session, or removed documentation.
One-off local checks can use disposable files/credentials without creating a new test
framework. Report whether a full disposable-VPS run was actually performed.

## Common change recipes

### Change application configuration or credentials

1. Locate its resource file and the Application that selects it. Check explicit
   include filters, namespace/name references, Secret field names and project policy.
2. Make the smallest edit. Preserve encrypted values unless changing those values is
   part of the request. Coordinate database-role passwords with Vault and sealed URLs.
3. Bump the Pod-template configuration revision when the change needs a new Pod.
4. Validate locally. Publishing/syncing is a separate production action.

### Add an application with persistent data or a database

Use the existing raw manifests and child Application pattern, with namespace `app-*`
and an appropriate resource budget. Include `CreateNamespace=true` when needed. Do not
assume adding files under an unreferenced directory creates a deployment. For a new
database, add its `{name, user}` entry and corresponding Vault mapping entry, then
coordinate its sealed connection string. For new persistent host data, define ownership,
backup inclusion and restoration together; a Deployment volume alone is not a backup.

### Change host paths or networking

Search the whole repository for all consumers. PostgreSQL bridge/port changes touch
Compose and EndpointSlice; media changes touch host directories, hostPath mounts,
backup defaults and recovery copies. Secret/resource renames can require resealing.
Pod CIDR or ingress-controller changes affect forwarded-header trust and NetworkPolicy.
Keep source-of-truth ownership intact instead of patching a generated object elsewhere.

## Production verification and handoff

The Hetzner firewall is managed manually, outside Ansible. On a provider change an
equivalent firewall is required, including IPv6 where present. HTTP/HTTPS need public
reachability; restrict SSH and Kubernetes API management access and avoid publicly
exposing PostgreSQL, kubelet, NodePorts or VXLAN. Repository configuration alone
cannot establish what the provider firewall or host firewall currently permits.

When live inspection is explicitly authorized, useful status checks include systemd
unit failures, K3s node/Pod readiness, Argo Application status, SealedSecret status,
public/private media behavior, database connectivity, certificate readiness and backup
service results. Inspect resource metadata rather than dumping Secrets. Successful
TCP/HTTP probes alone do not verify those access and recovery contracts.

Finish changes by reporting the files and behavior changed, the local checks actually
run, any required coordinated operator action, and what remains unverified. Do not
claim a successful production rollout, credential match, off-site backup or complete
restore unless it was actually checked. Keep the owner's README and unrelated work
untouched unless they asked otherwise.

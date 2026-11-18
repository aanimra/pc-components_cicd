"""Lab 5: DatabaseBackup -> CronJob reconciler with LIST/WATCH + periodic relist."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from kubernetes import client, config, watch
from kubernetes.client.exceptions import ApiException

LOG = logging.getLogger("databasebackup-controller")
GROUP = "backup.example.com"
VERSION = "v1alpha1"
PLURAL = "databasebackups"
NAMESPACE = os.getenv("WATCH_NAMESPACE", "demo")
POSTGRES_IMAGE = os.getenv("POSTGRES_CLIENT_IMAGE", "postgres:16-alpine")
WATCH_TIMEOUT = int(os.getenv("WATCH_TIMEOUT_SECONDS", "15"))

# The temporary file is on the same PVC, so renaming is atomic.
# On failure set -e exits with a non-zero status and the trap removes the partial dump.
BACKUP_SCRIPT = r"""set -eu
umask 077
mkdir -p /backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
final="/backups/${PGDATABASE}-${stamp}-${HOSTNAME}.dump"
temporary="${final}.tmp"
trap 'rm -f "$temporary"' EXIT
pg_dump -Fc --file="$temporary"
mv "$temporary" "$final"
trap - EXIT
echo "READY_BACKUP=$final"
"""


def desired_cronjob(backup: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic desired state from the current DatabaseBackup."""
    meta, spec = backup["metadata"], backup["spec"]
    name, ns = meta["name"], meta["namespace"]
    return {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {
            "name": name,
            "namespace": ns,
            "ownerReferences": [
                {
                    "apiVersion": f"{GROUP}/{VERSION}",
                    "kind": "DatabaseBackup",
                    "name": name,
                    "uid": meta["uid"],
                    "controller": True,
                }
            ],
        },
        "spec": {
            "schedule": spec["schedule"],
            "timeZone": spec.get("timeZone", "Etc/UTC"),
            "concurrencyPolicy": "Forbid",
            "jobTemplate": {
                "spec": {
                    "backoffLimit": 1,
                    "template": {
                        "spec": {
                            "restartPolicy": "Never",
                            "automountServiceAccountToken": False,
                            "containers": [
                                {
                                    "name": "pg-dump",
                                    "image": POSTGRES_IMAGE,
                                    "imagePullPolicy": "IfNotPresent",
                                    "command": ["/bin/sh", "-ec", BACKUP_SCRIPT],
                                    "envFrom": [
                                        {"secretRef": {"name": spec["connectionSecretName"]}}
                                    ],
                                    "volumeMounts": [
                                        {"name": "backups", "mountPath": "/backups"}
                                    ],
                                }
                            ],
                            "volumes": [
                                {
                                    "name": "backups",
                                    "persistentVolumeClaim": {
                                        "claimName": spec["backupPVCName"]
                                    },
                                }
                            ],
                        }
                    },
                }
            },
        },
    }


def contains_managed(actual: Any, desired: Any) -> bool:
    """Compare only managed fields, ignoring Kubernetes-injected defaults."""
    if isinstance(desired, dict):
        return isinstance(actual, dict) and all(
            key in actual and contains_managed(actual[key], value)
            for key, value in desired.items()
        )
    if isinstance(desired, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(desired)
            and all(contains_managed(a, d) for a, d in zip(actual, desired))
        )
    return actual == desired


def is_controlled_by(cronjob: dict[str, Any], backup: dict[str, Any]) -> bool:
    """Never claim someone else's CronJob, even if its name matches."""
    for owner in cronjob.get("metadata", {}).get("ownerReferences", []):
        if (
            owner.get("apiVersion") == f"{GROUP}/{VERSION}"
            and owner.get("kind") == "DatabaseBackup"
            and owner.get("uid") == backup["metadata"]["uid"]
            and owner.get("name") == backup["metadata"]["name"]
            and owner.get("controller") is True
        ):
            return True
    return False


def reconcile(name: str, custom: client.CustomObjectsApi, batch: client.BatchV1Api) -> None:
    """Re-read the current CR and repair missing/drifted owned CronJob."""
    try:
        backup = custom.get_namespaced_custom_object(
            GROUP, VERSION, NAMESPACE, PLURAL, name
        )
    except ApiException as exc:
        if exc.status == 404:
            LOG.info("DatabaseBackup deleted: %s/%s (Kubernetes GC owns cleanup)", NAMESPACE, name)
            return
        raise

    expected = desired_cronjob(backup)
    try:
        live_obj = batch.read_namespaced_cron_job(name, NAMESPACE)
    except ApiException as exc:
        if exc.status != 404:
            raise
        try:
            batch.create_namespaced_cron_job(NAMESPACE, expected)
            LOG.info("CREATED CronJob %s/%s", NAMESPACE, name)
        except ApiException as create_exc:
            if create_exc.status != 409:
                raise
            LOG.info("CronJob %s/%s appeared concurrently; retry on next scan", NAMESPACE, name)
        return

    live = client.ApiClient().sanitize_for_serialization(live_obj)
    if not is_controlled_by(live, backup):
        LOG.error("CONFLICT: CronJob %s/%s is not owned by this DatabaseBackup; unchanged", NAMESPACE, name)
        return
    if contains_managed(live.get("spec", {}), expected["spec"]):
        LOG.debug("UNCHANGED CronJob %s/%s", NAMESPACE, name)
        return

    # Only update the fields owned by our controller; no 'update' permission is needed.
    batch.patch_namespaced_cron_job(
        name,
        NAMESPACE,
        {"spec": expected["spec"]},
    )
    LOG.info("PATCHED CronJob %s/%s", NAMESPACE, name)


def list_then_watch(custom: client.CustomObjectsApi, batch: client.BatchV1Api) -> None:
    """LIST initial CRs; WATCH from the snapshot resourceVersion.

    Relisting after each 15-second stream provides full reconciliation,
    including recreation of CronJobs deleted independently of their CRs.
    """
    query = {"group": GROUP, "version": VERSION, "namespace": NAMESPACE, "plural": PLURAL}
    snapshot = custom.list_namespaced_custom_object(**query)
    items = snapshot.get("items", [])
    for item in items:
        try:
            reconcile(item["metadata"]["name"], custom, batch)
        except ApiException:
            LOG.exception("Reconcile failed for %s/%s", NAMESPACE, item["metadata"]["name"])
    version = snapshot["metadata"]["resourceVersion"]
    LOG.info("LIST %s DatabaseBackup objects (resourceVersion=%s)", len(items), version)

    stream = watch.Watch()
    try:
        for event in stream.stream(
            custom.list_namespaced_custom_object,
            **query,
            resource_version=version,
            timeout_seconds=WATCH_TIMEOUT,
        ):
            event_type = event.get("type")
            item = event.get("object") or {}
            if event_type == "ERROR":
                if item.get("code") == 410:
                    LOG.warning("410 Gone: relisting DatabaseBackup resources")
                    return
                raise RuntimeError(f"Kubernetes watch error: {item}")
            if event_type in {"ADDED", "MODIFIED", "DELETED"}:
                name = item.get("metadata", {}).get("name")
                if name:
                    LOG.info("EVENT %s %s/%s", event_type, NAMESPACE, name)
                    try:
                        reconcile(name, custom, batch)
                    except ApiException:
                        LOG.exception("Reconcile failed for %s/%s", NAMESPACE, name)
    finally:
        stream.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config.load_incluster_config()
    custom = client.CustomObjectsApi()
    batch = client.BatchV1Api()
    LOG.info("Starting DatabaseBackup controller in namespace %s", NAMESPACE)
    while True:
        try:
            list_then_watch(custom, batch)
        except ApiException as exc:
            if exc.status == 410:
                LOG.warning("410 Gone: resuming from new LIST")
                continue
            LOG.exception("Kubernetes API error (retrying)")
            time.sleep(3)
        except Exception:
            LOG.exception("Unexpected controller failure (retrying)")
            time.sleep(3)


if __name__ == "__main__":
    main()

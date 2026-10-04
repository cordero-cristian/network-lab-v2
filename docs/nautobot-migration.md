# Nautobot 3.2.5 Migration

This lab upgrades directly from Nautobot 2.4.41 to 3.2.5. Nautobot's v3.2.5 upgrade
guide recommends separate production steps but requires only Nautobot 2.4.15 or newer
before v3 for the job-approval check. This deployment has no Apps or Jobs and already
meets that prerequisite, so an intermediate 2.4.42 image adds no required migration.

## Backup And Trial

Stop Nautobot writers, then record the current image/version and Django migration list.
Create a PostgreSQL custom-format dump and an archive of the complete
`nautobot-media` volume. Keep their checksums with the migration evidence.

Restore copies of both backups into a disposable Compose project and run the normal
initializer there first. The initializer remains the sole owner of:

```sh
nautobot-server post_upgrade
```

Do not use the retained `network-lab` volumes for the first 3.2.5 attempt. The trial is
successful only when init exits zero; web, worker, and scheduler are healthy; the image
and `/api/status/` report 3.2.5; authenticated responses report `API-Version: 3.2`; the
canonical user remains a superuser; and retained reciprocal cable endpoints still
produce the expected physical topology link.

## Retained Upgrade

After the restored trial passes, stop Nautobot web, worker, and scheduler, verify the
backups again, and start the updated Compose stack. Preserve the service names,
dependencies, PostgreSQL volume, media volume, and init ordering. Validate fixture
create/cleanup and the bounded Features 002, 003, 004, and 006 acceptance paths before
declaring the migration complete.

## Rollback

Stop all Nautobot processes before rollback. Restore the pre-upgrade PostgreSQL dump
into a clean matching database volume, restore the matching media archive, restore all
four `networktocode/nautobot:2.4.41-py3.12` image pins, and then run the old initializer
and health checks. Never point 2.4.41 at a database already migrated by 3.2.5, and never
treat an image-only downgrade as rollback.

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.audit.operations import OperationRecord
from app.candidates.models import AutomaticResult
from app.config import get_settings
from app.db import Base
from app.errors.models import ErrorRecord
from app.jobs.idempotency import LogicalJob
from app.projects.models import Project
from app.review.models import ReviewLock, ReviewWorkingCopy
from app.storage.models import StoredFile


config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata

# Imports above register all current models on the shared metadata.
assert {
    Project,
    StoredFile,
    OperationRecord,
    LogicalJob,
    ErrorRecord,
    AutomaticResult,
    ReviewWorkingCopy,
    ReviewLock,
}


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

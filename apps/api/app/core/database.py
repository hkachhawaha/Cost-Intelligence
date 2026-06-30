"""Async SQLAlchemy engine, session factory, and the RLS-injecting session
dependency.

`get_session` is the FastAPI dependency for request handlers; `session_for_tenant`
is for code outside an HTTP request (Celery workers, scripts) where the caller
owns the session lifecycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.tenancy import apply_rls, current_tenant

if settings.environment == "test":
    # NullPool: never reuse a connection across event loops. pytest-asyncio gives
    # each test its own loop, and a pooled connection bound to a closed loop would
    # raise "Event loop is closed". No pooling needed for the test workload.
    engine = create_async_engine(str(settings.database_url), poolclass=NullPool)
else:
    engine = create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # recycle dead connections (RDS failover safe)
        echo=False,
    )

SessionFactory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Opens a session, binds the current tenant for RLS,
    yields, commits on success, rolls back on error. The RLS binding is
    transaction-local, so it cannot leak across the connection pool."""
    tenant_id = current_tenant.get()
    async with SessionFactory() as session:
        try:
            if tenant_id is not None:
                await apply_rls(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def session_for_tenant(tenant_id: str) -> AsyncSession:
    """For use OUTSIDE an HTTP request (Celery workers, scripts). Caller owns the
    session lifecycle. RLS is applied immediately."""
    session = SessionFactory()
    await apply_rls(session, tenant_id)
    return session

"""Deposit and withdrawal routes — full on-chain fund management."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, field_validator

from api.auth import require_api_key
from config import get_settings
from services.database import DatabaseService
from services.exchange import ExchangeService
from services.redis_service import get_redis_client

settings = get_settings()

router = APIRouter(
    prefix="/funds",
    tags=["funds"],
    dependencies=[Depends(require_api_key)],
)

# ── Input validation patterns ─────────────────────────────────────────────────

_CURRENCY_RE = re.compile(r"^[A-Z0-9]{1,10}$")
_NETWORK_RE = re.compile(r"^[A-Za-z0-9]{1,30}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_WITHDRAW_COOLDOWN = 60  # seconds — enforced in Redis so it works across workers


class WithdrawRequest(BaseModel):
    currency: str
    amount: float
    address: str
    tag: Optional[str] = None
    network: Optional[str] = None

    @field_validator("currency")
    @classmethod
    def _val_currency(cls, v: str) -> str:
        v = v.strip().upper()
        if not _CURRENCY_RE.match(v):
            raise ValueError("currency must be 1-10 uppercase alphanumeric chars")
        return v

    @field_validator("amount")
    @classmethod
    def _val_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be positive")
        if v > 10_000_000:
            raise ValueError("amount exceeds single-withdrawal cap")
        return v

    @field_validator("address")
    @classmethod
    def _val_address(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 6 or len(v) > 200:
            raise ValueError("address must be 6-200 characters")
        if _CONTROL_RE.search(v):
            raise ValueError("address contains invalid characters")
        return v

    @field_validator("tag")
    @classmethod
    def _val_tag(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        if not re.match(r"^[A-Za-z0-9]{1,50}$", v):
            raise ValueError("tag must be alphanumeric, max 50 chars")
        return v

    @field_validator("network")
    @classmethod
    def _val_network(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        if not _NETWORK_RE.match(v):
            raise ValueError("network must be alphanumeric, max 30 chars")
        return v


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/balances")
async def get_balances():
    """Full coin balance breakdown: free, locked, total per currency."""
    exchange = ExchangeService()
    try:
        raw = await exchange.fetch_balance()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Exchange error: {exc}")
    finally:
        await exchange.close()

    total_map = raw.get("total", {})
    free_map = raw.get("free", {})
    used_map = raw.get("used", {})

    coins = []
    for currency, total in total_map.items():
        if currency in ("info", "timestamp", "datetime"):
            continue
        if not isinstance(total, (int, float)) or total <= 0:
            continue
        coins.append({
            "currency": currency,
            "free": float(free_map.get(currency) or 0),
            "locked": float(used_map.get(currency) or 0),
            "total": float(total),
        })

    coins.sort(key=lambda x: x["total"], reverse=True)
    return {"balances": coins, "exchange": settings.exchange_id}


@router.get("/deposit-address")
async def get_deposit_address(currency: str, network: Optional[str] = None):
    """Get on-chain deposit address for a currency/network pair."""
    currency = currency.strip().upper()
    if not _CURRENCY_RE.match(currency):
        raise HTTPException(status_code=400, detail="Invalid currency")
    if network:
        network = network.strip()
        if not _NETWORK_RE.match(network):
            raise HTTPException(status_code=400, detail="Invalid network")

    exchange = ExchangeService()
    try:
        result = await exchange.fetch_deposit_address(currency, network)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Exchange error: {exc}")
    finally:
        await exchange.close()

    return {
        "currency": currency,
        "address": result.get("address", ""),
        "tag": result.get("tag"),
        "network": result.get("network") or network,
    }


@router.get("/deposits")
async def get_deposits(currency: Optional[str] = None, limit: int = 20):
    """Fetch deposit history from the exchange."""
    limit = max(1, min(100, limit))
    if currency:
        currency = currency.strip().upper()
        if not _CURRENCY_RE.match(currency):
            raise HTTPException(status_code=400, detail="Invalid currency")

    exchange = ExchangeService()
    try:
        txs = await exchange.fetch_deposits(currency, limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Exchange error: {exc}")
    finally:
        await exchange.close()

    return {"deposits": [_norm_tx(t, "deposit") for t in txs], "count": len(txs)}


@router.post("/withdraw")
async def post_withdraw(request: Request, body: WithdrawRequest):
    """Submit a withdrawal. Rate-limited to 1 per 60 s per IP (Redis-backed)."""
    ip = _client_ip(request)
    redis = get_redis_client()
    rate_key = f"sfomo:withdraw_rl:{ip}"
    # SET NX EX is atomic — safe across multiple workers/processes
    acquired = await redis.set(rate_key, "1", nx=True, ex=_WITHDRAW_COOLDOWN)
    if not acquired:
        ttl = await redis.ttl(rate_key)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: wait {max(1, ttl)}s before next withdrawal",
        )

    db = DatabaseService()
    exchange = ExchangeService()
    try:
        logger.warning(
            f"[Funds] withdrawal: {body.amount} {body.currency} → "
            f"{body.address[:16]}... net={body.network} ip={ip}"
        )
        result = await exchange.withdraw(
            currency=body.currency,
            amount=body.amount,
            address=body.address,
            tag=body.tag,
            network=body.network,
        )
        wid = str(result.get("id", ""))
        await db.record_audit_log(
            action="withdrawal",
            symbol=body.currency,
            side="out",
            size=body.amount,
            order_id=wid,
            status="submitted",
            detail=f"addr={body.address[:20]} net={body.network}",
            cycle_id="",
        )
        return {
            "status": "submitted",
            "id": wid,
            "currency": body.currency,
            "amount": body.amount,
            "address": body.address,
            "network": body.network,
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.record_audit_log(
            action="withdrawal_failed",
            symbol=body.currency,
            side="out",
            size=body.amount,
            status="failed",
            detail=str(exc)[:200],
            cycle_id="",
        )
        logger.error(f"[Funds] withdrawal failed: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Exchange error: {exc}")
    finally:
        await exchange.close()


@router.get("/withdrawals")
async def get_withdrawals(currency: Optional[str] = None, limit: int = 20):
    """Fetch withdrawal history from the exchange."""
    limit = max(1, min(100, limit))
    if currency:
        currency = currency.strip().upper()
        if not _CURRENCY_RE.match(currency):
            raise HTTPException(status_code=400, detail="Invalid currency")

    exchange = ExchangeService()
    try:
        txs = await exchange.fetch_withdrawals(currency, limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Exchange error: {exc}")
    finally:
        await exchange.close()

    return {"withdrawals": [_norm_tx(t, "withdrawal") for t in txs], "count": len(txs)}


# ── Normaliser ────────────────────────────────────────────────────────────────

def _norm_tx(tx: dict, tx_type: str) -> dict:
    ts = tx.get("datetime") or tx.get("timestamp")
    if isinstance(ts, (int, float)):
        from datetime import datetime, timezone
        ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    fee_raw = tx.get("fee")
    fee = float(fee_raw.get("cost") or 0) if isinstance(fee_raw, dict) else 0.0
    return {
        "id": tx.get("id", ""),
        "type": tx_type,
        "currency": tx.get("currency", ""),
        "amount": float(tx.get("amount") or 0),
        "address": tx.get("address", ""),
        "tag": tx.get("tag"),
        "txid": tx.get("txid", ""),
        "network": tx.get("network"),
        "status": tx.get("status", ""),
        "fee": fee,
        "timestamp": ts,
    }

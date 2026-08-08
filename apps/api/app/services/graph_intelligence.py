from __future__ import annotations

from dataclasses import dataclass, field

from neo4j import AsyncGraphDatabase

from app.core.config import get_settings


@dataclass(frozen=True)
class GraphInvestigationResult:
    available: bool
    transaction_found: bool

    shared_device_transactions: int = 0
    linked_accounts: int = 0
    linked_customers: int = 0
    risky_merchant_transactions: int = 0
    prior_high_risk_transactions: int = 0

    graph_risk_score: float = 0.0
    indicators: list[str] = field(default_factory=list)
    warning: str | None = None


GRAPH_QUERY = """
MATCH (t:Transaction {id: $transaction_id})

OPTIONAL MATCH
    (t)-[:USED_DEVICE]->(device:Device)
        <-[:USED_DEVICE]-(device_tx:Transaction)
        <-[:INITIATED]-(device_account:Account)
        <-[:OWNS]-(device_customer:Customer)

OPTIONAL MATCH
    (t)-[:AT_MERCHANT]->(merchant:Merchant)
        <-[:AT_MERCHANT]-(merchant_tx:Transaction)

OPTIONAL MATCH
    (current_account:Account)-[:INITIATED]->(t)

OPTIONAL MATCH
    (current_account)-[:INITIATED]->(prior_tx:Transaction)

WITH
    t,
    collect(
        DISTINCT CASE
            WHEN device_tx.id <> t.id
            THEN device_tx.id
        END
    ) AS shared_device_tx_ids,

    collect(
        DISTINCT CASE
            WHEN device_tx.id <> t.id
            AND device_account.id <> current_account.id
            THEN device_account.id
        END
    ) AS linked_account_ids,

    collect(
        DISTINCT CASE
            WHEN device_tx.id <> t.id
            THEN device_customer.external_id
        END
    ) AS linked_customer_ids,

    collect(
        DISTINCT CASE
            WHEN merchant_tx.id <> t.id
            AND (
                coalesce(merchant_tx.fraud_probability, 0.0) >= 0.65
                OR merchant_tx.status IN ['blocked', 'review']
            )
            THEN merchant_tx.id
        END
    ) AS risky_merchant_tx_ids,

    collect(
        DISTINCT CASE
            WHEN prior_tx.id <> t.id
            AND (
                coalesce(prior_tx.fraud_probability, 0.0) >= 0.65
                OR prior_tx.status IN ['blocked', 'review']
            )
            THEN prior_tx.id
        END
    ) AS prior_high_risk_tx_ids

RETURN
    size([x IN shared_device_tx_ids WHERE x IS NOT NULL])
        AS shared_device_transactions,

    size([x IN linked_account_ids WHERE x IS NOT NULL])
        AS linked_accounts,

    size([x IN linked_customer_ids WHERE x IS NOT NULL])
        AS linked_customers,

    size([x IN risky_merchant_tx_ids WHERE x IS NOT NULL])
        AS risky_merchant_transactions,

    size([x IN prior_high_risk_tx_ids WHERE x IS NOT NULL])
        AS prior_high_risk_transactions
"""


def _calculate_graph_risk(
    *,
    shared_device_transactions: int,
    linked_accounts: int,
    linked_customers: int,
    risky_merchant_transactions: int,
    prior_high_risk_transactions: int,
) -> tuple[float, list[str]]:
    score = 0.0
    indicators: list[str] = []

    if shared_device_transactions > 0:
        score += min(0.25, 0.08 * shared_device_transactions)
        indicators.append(
            f"Device is shared with {shared_device_transactions} other transaction(s)."
        )

    if linked_accounts > 0:
        score += min(0.25, 0.12 * linked_accounts)
        indicators.append(
            f"Shared-device activity links {linked_accounts} additional account(s)."
        )

    if linked_customers > 0:
        score += min(0.20, 0.10 * linked_customers)
        indicators.append(
            f"Graph traversal links {linked_customers} additional customer(s)."
        )

    if risky_merchant_transactions > 0:
        score += min(0.25, 0.10 * risky_merchant_transactions)
        indicators.append(
            f"Merchant is connected to {risky_merchant_transactions} other high-risk transaction(s)."
        )

    if prior_high_risk_transactions > 0:
        score += min(0.30, 0.12 * prior_high_risk_transactions)
        indicators.append(
            f"Account has {prior_high_risk_transactions} other high-risk transaction(s)."
        )

    return min(round(score, 4), 1.0), indicators


async def investigate_transaction_graph(
    transaction_id: str,
) -> GraphInvestigationResult:
    """
    Query Neo4j for fraud-network relationships surrounding one transaction.

    The function intentionally degrades gracefully when Neo4j is unavailable
    so graph infrastructure failure does not crash the full fraud workflow.
    """

    settings = get_settings()

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password,
        ),
    )

    try:
        async with driver.session() as session:
            result = await session.run(
                GRAPH_QUERY,
                transaction_id=str(transaction_id),
            )

            record = await result.single()

        if record is None:
            return GraphInvestigationResult(
                available=True,
                transaction_found=False,
                warning=(
                    "Transaction was not found in the Neo4j banking graph."
                ),
            )

        shared_device_transactions = int(
            record["shared_device_transactions"] or 0
        )
        linked_accounts = int(record["linked_accounts"] or 0)
        linked_customers = int(record["linked_customers"] or 0)
        risky_merchant_transactions = int(
            record["risky_merchant_transactions"] or 0
        )
        prior_high_risk_transactions = int(
            record["prior_high_risk_transactions"] or 0
        )

        graph_risk_score, indicators = _calculate_graph_risk(
            shared_device_transactions=shared_device_transactions,
            linked_accounts=linked_accounts,
            linked_customers=linked_customers,
            risky_merchant_transactions=risky_merchant_transactions,
            prior_high_risk_transactions=prior_high_risk_transactions,
        )

        return GraphInvestigationResult(
            available=True,
            transaction_found=True,
            shared_device_transactions=shared_device_transactions,
            linked_accounts=linked_accounts,
            linked_customers=linked_customers,
            risky_merchant_transactions=risky_merchant_transactions,
            prior_high_risk_transactions=prior_high_risk_transactions,
            graph_risk_score=graph_risk_score,
            indicators=indicators,
        )

    except Exception as exc:
        return GraphInvestigationResult(
            available=False,
            transaction_found=False,
            warning=f"Neo4j graph investigation unavailable: {type(exc).__name__}",
        )

    finally:
        await driver.close()

from __future__ import annotations

import os

from neo4j import GraphDatabase
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.banking import Account, Customer, Transaction


def enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def create_constraints(driver) -> None:
    """Create unique graph constraints so repeated syncs remain idempotent."""

    queries = [
        """
        CREATE CONSTRAINT customer_external_id IF NOT EXISTS
        FOR (c:Customer)
        REQUIRE c.external_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT account_id IF NOT EXISTS
        FOR (a:Account)
        REQUIRE a.id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT transaction_id IF NOT EXISTS
        FOR (t:Transaction)
        REQUIRE t.id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT merchant_id IF NOT EXISTS
        FOR (m:Merchant)
        REQUIRE m.merchant_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT device_id IF NOT EXISTS
        FOR (d:Device)
        REQUIRE d.device_id IS UNIQUE
        """,
    ]

    for query in queries:
        driver.execute_query(query)


def sync_customer(driver, customer: Customer) -> None:
    driver.execute_query(
        """
        MERGE (c:Customer {external_id: $external_id})
        SET
            c.full_name = $full_name,
            c.country_code = $country_code,
            c.risk_level = $risk_level,
            c.kyc_verified = $kyc_verified,
            c.is_pep = $is_pep,
            c.sanctions_match = $sanctions_match
        """,
        external_id=customer.external_id,
        full_name=customer.full_name,
        country_code=customer.country_code,
        risk_level=enum_value(customer.risk_level),
        kyc_verified=bool(customer.kyc_verified),
        is_pep=bool(customer.is_pep),
        sanctions_match=bool(customer.sanctions_match),
    )


def sync_account(
    driver,
    account: Account,
    customer: Customer,
) -> None:
    driver.execute_query(
        """
        MATCH (c:Customer {external_id: $customer_external_id})

        MERGE (a:Account {id: $account_id})
        SET
            a.account_number_token = $account_number_token,
            a.account_type = $account_type,
            a.status = $status,
            a.balance = $balance,
            a.currency = $currency

        MERGE (c)-[:OWNS]->(a)
        """,
        customer_external_id=customer.external_id,
        account_id=str(account.id),
        account_number_token=account.account_number_token,
        account_type=account.account_type,
        status=enum_value(account.status),
        balance=float(account.balance),
        currency=account.currency,
    )


def sync_transaction(
    driver,
    transaction: Transaction,
    account: Account,
) -> None:
    metadata = transaction.metadata_json or {}

    driver.execute_query(
        """
        MATCH (a:Account {id: $account_id})

        MERGE (t:Transaction {id: $transaction_id})
        SET
            t.external_id = $external_id,
            t.amount = $amount,
            t.currency = $currency,
            t.transaction_type = $transaction_type,
            t.status = $status,
            t.ip_risk_score = $ip_risk_score,
            t.merchant_risk_score = $merchant_risk_score,
            t.anomaly_score = $anomaly_score,
            t.fraud_probability = $fraud_probability,
            t.amount_zscore = $amount_zscore,
            t.velocity_1h = $velocity_1h,
            t.country = $country,
            t.is_cross_border = $is_cross_border

        MERGE (a)-[:INITIATED]->(t)

        WITH t

        FOREACH (_ IN CASE
            WHEN $merchant_id IS NOT NULL THEN [1]
            ELSE []
        END |
            MERGE (m:Merchant {merchant_id: $merchant_id})
            SET m.risk_score = $merchant_risk_score
            MERGE (t)-[:AT_MERCHANT]->(m)
        )

        FOREACH (_ IN CASE
            WHEN $device_id IS NOT NULL THEN [1]
            ELSE []
        END |
            MERGE (d:Device {device_id: $device_id})
            SET d.known = $device_known
            MERGE (t)-[:USED_DEVICE]->(d)
        )
        """,
        account_id=str(account.id),
        transaction_id=str(transaction.id),
        external_id=transaction.external_id,
        amount=float(transaction.amount),
        currency=transaction.currency,
        transaction_type=transaction.transaction_type,
        status=enum_value(transaction.status),
        ip_risk_score=float(transaction.ip_risk_score or 0.0),
        merchant_risk_score=float(transaction.merchant_risk_score or 0.0),
        anomaly_score=float(transaction.anomaly_score or 0.0),
        fraud_probability=float(transaction.fraud_probability or 0.0),
        amount_zscore=float(transaction.amount_zscore or 0.0),
        velocity_1h=int(transaction.velocity_1h or 0),
        country=str(metadata.get("country", "")),
        is_cross_border=bool(metadata.get("is_cross_border", False)),
        merchant_id=transaction.merchant_id,
        device_id=transaction.device_id,
        device_known=bool(transaction.device_known),
    )


def main() -> None:
    settings = get_settings()

    engine = create_engine(os.environ["DATABASE_URL"])

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(
            settings.neo4j_user,
            settings.neo4j_password,
        ),
    )

    driver.verify_connectivity()
    create_constraints(driver)

    customer_count = 0
    account_count = 0
    transaction_count = 0

    with Session(engine) as db:
        customers = db.scalars(select(Customer)).all()

        for customer in customers:
            sync_customer(driver, customer)
            customer_count += 1

        accounts = db.scalars(select(Account)).all()

        for account in accounts:
            customer = db.get(Customer, account.customer_id)

            if customer is None:
                continue

            sync_account(driver, account, customer)
            account_count += 1

        transactions = db.scalars(select(Transaction)).all()

        for transaction in transactions:
            account = db.get(Account, transaction.account_id)

            if account is None:
                continue

            sync_transaction(driver, transaction, account)
            transaction_count += 1

    driver.close()

    print("FinSentinel banking graph synchronization complete.")
    print("Customers:", customer_count)
    print("Accounts:", account_count)
    print("Transactions:", transaction_count)


if __name__ == "__main__":
    main()

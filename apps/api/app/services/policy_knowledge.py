from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

COLLECTION_NAME = "finsentinel_policies"
EMBEDDING_MODEL = "BAAI/bge-small-en"


POLICIES = [
    {
        "policy_id": "FRD-001",
        "title": "High-Risk Transaction Manual Review",
        "category": "fraud",
        "severity": "high",
        "document": (
            "Transactions with a combined fraud risk score of 0.65 or greater "
            "must be escalated for human fraud analyst review. Critical-risk "
            "transactions may be blocked while review is pending."
        ),
    },
    {
        "policy_id": "FRD-002",
        "title": "Shared Device Fraud Network Escalation",
        "category": "fraud",
        "severity": "critical",
        "document": (
            "Transactions using a device connected to other customer accounts "
            "require enhanced fraud investigation, especially when linked to "
            "high-risk merchants or abnormal transaction activity."
        ),
    },
    {
        "policy_id": "FRD-003",
        "title": "High-Risk Merchant Monitoring",
        "category": "fraud",
        "severity": "high",
        "document": (
            "Transactions involving merchants with elevated historical fraud "
            "risk require additional monitoring and network investigation."
        ),
    },
    {
        "policy_id": "AML-001",
        "title": "Suspicious Activity Escalation",
        "category": "aml",
        "severity": "critical",
        "document": (
            "Unusual transaction velocity, behavioral outliers, suspicious "
            "linked entities, or repeated high-risk transfers require enhanced "
            "AML investigation."
        ),
    },
    {
        "policy_id": "AML-002",
        "title": "Cross-Customer Network Risk",
        "category": "aml",
        "severity": "high",
        "document": (
            "Multiple customers or accounts connected through shared devices, "
            "merchants, or transaction infrastructure must be evaluated for "
            "coordinated suspicious activity."
        ),
    },
    {
        "policy_id": "GOV-001",
        "title": "Human Oversight for High-Risk AI Decisions",
        "category": "governance",
        "severity": "critical",
        "document": (
            "High or critical risk AI-generated banking decisions must preserve "
            "human oversight and record model output, agent evidence, policy "
            "evidence, final recommendation, and reviewer decision."
        ),
    },
    {
        "policy_id": "GOV-002",
        "title": "Model Decision Traceability",
        "category": "governance",
        "severity": "high",
        "document": (
            "Fraud predictions used in governed decisions must retain model "
            "version, fraud probability, anomaly signal, risk factors, and "
            "investigation results for traceability."
        ),
    },
    {
        "policy_id": "CRD-001",
        "title": "Credit Decision Manual Review",
        "category": "credit",
        "severity": "high",
        "document": (
            "Credit applications with elevated model risk, insufficient "
            "confidence, or conflicting underwriting signals must be routed "
            "to manual review."
        ),
    },
]


@dataclass(frozen=True)
class PolicyMatch:
    policy_id: str
    title: str
    category: str
    severity: str
    document: str
    similarity_score: float


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
        timeout=30,
    )


def index_policy_knowledge() -> int:
    client = get_qdrant_client()

    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=client.get_embedding_size(EMBEDDING_MODEL),
            distance=models.Distance.COSINE,
        ),
    )

    client.upload_collection(
        collection_name=COLLECTION_NAME,
        vectors=[
            models.Document(
                text=policy["document"],
                model=EMBEDDING_MODEL,
            )
            for policy in POLICIES
        ],
        payload=[
            {
                **policy,
                "knowledge_source": "synthetic_finsentinel_policy",
            }
            for policy in POLICIES
        ],
        ids=[
            str(
                uuid5(
                    NAMESPACE_URL,
                    f"finsentinel:{policy['policy_id']}",
                )
            )
            for policy in POLICIES
        ],
    )

    return len(POLICIES)


def search_policies(
    query: str,
    top_k: int = 3,
) -> list[PolicyMatch]:
    client = get_qdrant_client()

    if not client.collection_exists(COLLECTION_NAME):
        return []

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=models.Document(
            text=query,
            model=EMBEDDING_MODEL,
        ),
        limit=top_k,
        with_payload=True,
    )

    matches: list[PolicyMatch] = []

    for point in result.points:
        payload = point.payload or {}

        matches.append(
            PolicyMatch(
                policy_id=str(payload.get("policy_id", "UNKNOWN")),
                title=str(payload.get("title", "Unknown policy")),
                category=str(payload.get("category", "unknown")),
                severity=str(payload.get("severity", "unknown")),
                document=str(payload.get("document", "")),
                similarity_score=round(float(point.score), 4),
            )
        )

    return matches

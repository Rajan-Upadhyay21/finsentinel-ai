from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.orchestrator import run_investigation
from app.core.audit_identity import principal_audit_details
from app.core.permissions import (
    Permission,
    ensure_permission,
    ensure_workflow_decision_permission,
)
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.banking import (
    Account,
    Approval,
    ApprovalStatus,
    AuditLog,
    CaseStatus,
    CaseType,
    Customer,
    InvestigationCase,
    LoanApplication,
    Transaction,
    TransactionStatus,
)
from app.schemas.banking import (
    AccountCreate,
    AccountRead,
    ApprovalRead,
    AuditLogRead,
    CustomerCreate,
    CustomerRead,
    InvestigationCaseRead,
    LoanApplicationCreate,
    LoanApplicationRead,
    TransactionCreate,
    TransactionRead,
)
from app.schemas.investigation import InvestigationDecision, InvestigationRequest
from app.schemas.transaction import TransactionFeatures

router = APIRouter(
    prefix="/api/v1/banking",
    tags=["banking"],
)


class ApprovalReviewRequest(BaseModel):
    """Human review payload for a pending AI-generated approval."""

    reviewer_id: str | None = Field(default=None, min_length=1, max_length=128)
    approved: bool
    reviewer_comment: str | None = Field(default=None, max_length=2000)


def _commit_or_rollback(db: Session) -> None:
    """Commit a unit of work and rollback if SQLAlchemy fails."""
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


# ============================================================
# CUSTOMERS
# ============================================================


@router.post(
    "/customers",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    current_user: CurrentUser,
    payload: CustomerCreate,
    db: Session = Depends(get_db),
) -> Customer:
    ensure_permission(current_user, Permission.PLATFORM_ADMIN)
    """Create a new banking customer."""

    customer = Customer(
        external_id=payload.external_id,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else None,
        phone_token=payload.phone_token,
        country_code=payload.country_code.upper(),
        risk_level=payload.risk_level,
        kyc_verified=payload.kyc_verified,
        is_pep=payload.is_pep,
        sanctions_match=payload.sanctions_match,
    )

    db.add(customer)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer with this external_id already exists.",
        ) from exc

    db.refresh(customer)
    return customer


@router.get(
    "/customers",
    response_model=list[CustomerRead],
)
def list_customers(
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Customer]:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Return banking customers using pagination."""

    statement = (
        select(Customer)
        .order_by(Customer.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerRead,
)
def get_customer(
    current_user: CurrentUser,
    customer_id: UUID,
    db: Session = Depends(get_db),
) -> Customer:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Retrieve one customer by internal UUID."""

    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )
    return customer


# ============================================================
# ACCOUNTS
# ============================================================


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    current_user: CurrentUser,
    payload: AccountCreate,
    db: Session = Depends(get_db),
) -> Account:
    ensure_permission(current_user, Permission.PLATFORM_ADMIN)
    """Create a bank account linked to an existing customer."""

    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    account = Account(
        customer_id=payload.customer_id,
        account_number_token=payload.account_number_token,
        account_type=payload.account_type,
        status=payload.status,
        balance=payload.balance,
        currency=payload.currency.upper(),
    )

    db.add(account)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account with this token already exists.",
        ) from exc

    db.refresh(account)
    return account


@router.get(
    "/accounts",
    response_model=list[AccountRead],
)
def list_accounts(
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Account]:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Return bank accounts using pagination."""

    statement = (
        select(Account)
        .order_by(Account.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get(
    "/accounts/{account_id}",
    response_model=AccountRead,
)
def get_account(
    current_user: CurrentUser,
    account_id: UUID,
    db: Session = Depends(get_db),
) -> Account:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Retrieve one account by internal UUID."""

    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )
    return account


# ============================================================
# TRANSACTIONS
# ============================================================


@router.post(
    "/transactions",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    current_user: CurrentUser,
    payload: TransactionCreate,
    db: Session = Depends(get_db),
) -> Transaction:
    ensure_permission(current_user, Permission.PLATFORM_ADMIN)
    """Create a banking transaction linked to an existing account."""

    account = db.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )

    transaction = Transaction(
        external_id=payload.external_id,
        account_id=payload.account_id,
        merchant_id=payload.merchant_id,
        amount=payload.amount,
        currency=payload.currency.upper(),
        transaction_type=payload.transaction_type,
        status=payload.status,
        device_id=payload.device_id,
        device_known=payload.device_known,
        ip_address_token=payload.ip_address_token,
        ip_risk_score=payload.ip_risk_score,
        merchant_risk_score=payload.merchant_risk_score,
        anomaly_score=payload.anomaly_score,
        fraud_probability=payload.fraud_probability,
        amount_zscore=payload.amount_zscore,
        velocity_1h=payload.velocity_1h,
        occurred_at=payload.occurred_at,
        metadata_json=payload.metadata_json,
    )

    db.add(transaction)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction with this external_id already exists.",
        ) from exc

    db.refresh(transaction)
    return transaction


@router.get(
    "/transactions",
    response_model=list[TransactionRead],
)
def list_transactions(
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Return banking transactions using pagination."""

    statement = (
        select(Transaction)
        .order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionRead,
)
def get_transaction(
    current_user: CurrentUser,
    transaction_id: UUID,
    db: Session = Depends(get_db),
) -> Transaction:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Retrieve one transaction by internal UUID."""

    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found.",
        )
    return transaction


# ============================================================
# TRANSACTION -> MULTI-AGENT INVESTIGATION
# ============================================================


@router.post(
    "/transactions/{transaction_id}/investigate",
    response_model=InvestigationDecision,
)
async def investigate_stored_transaction(
    current_user: CurrentUser,
    transaction_id: UUID,
    db: Session = Depends(get_db),
) -> InvestigationDecision:
    ensure_permission(current_user, Permission.FRAUD_INVESTIGATE)
    """
    Load a persisted transaction, execute the fraud investigation workflow,
    and persist the governed case, approval request, audit record and
    transaction risk outcome.
    """

    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found.",
        )

    account = db.get(Account, transaction.account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account linked to transaction was not found.",
        )

    customer = db.get(Customer, account.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer linked to account was not found.",
        )

    metadata = transaction.metadata_json or {}

    transaction_country = str(
        metadata.get("country", customer.country_code)
    ).upper()
    customer_country = str(customer.country_code).upper()

    is_cross_border = bool(
        metadata.get(
            "is_cross_border",
            transaction_country != customer_country,
        )
    )

    def age_in_days(value: datetime | None) -> int:
        if value is None:
            return 0

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return max(
            (datetime.now(timezone.utc) - value).days,
            0,
        )

    features = TransactionFeatures(
        transaction_id=transaction.id,
        customer_id=customer.external_id,
        account_id=account.account_number_token,
        merchant_id=transaction.merchant_id or "UNKNOWN-MERCHANT",
        amount=transaction.amount,
        currency=transaction.currency,
        country_code=transaction_country,
        is_cross_border=is_cross_border,
        account_age_days=age_in_days(account.created_at),
        customer_tenure_days=age_in_days(customer.created_at),
        device_known=transaction.device_known,
        ip_risk_score=float(transaction.ip_risk_score),
        merchant_risk_score=float(transaction.merchant_risk_score),
        amount_zscore=float(transaction.amount_zscore),
        velocity_1h=transaction.velocity_1h,
        timestamp=(
            transaction.occurred_at
            or transaction.created_at
            or datetime.now(timezone.utc)
        ),
    )

    request = InvestigationRequest(
        workflow="fraud",
        transaction=features,
    )

    decision = await run_investigation(request)
    decision_payload = decision.model_dump(mode="json")

    # Flatten agent evidence into the case evidence field.
    evidence_payload: list[dict] = []
    for finding in decision_payload.get("findings", []):
        for evidence in finding.get("evidence", []):
            evidence_payload.append(
                {
                    "agent": finding.get("agent"),
                    **evidence,
                }
            )

    # Keep the database case ID aligned with the orchestrator case ID.
    case = InvestigationCase(
        id=UUID(str(decision.case_id)),
        case_type=CaseType.FRAUD,
        subject_id=str(transaction.id),
        status=(
            CaseStatus.PENDING_APPROVAL
            if decision.transaction_score.requires_human_review
            else CaseStatus.RESOLVED
        ),
        risk_score=decision.transaction_score.combined_risk_score,
        confidence_score=decision.final_confidence,
        assigned_role="fraud_analyst",
        recommended_action=str(decision.decision),
        summary=decision.rationale,
        evidence=evidence_payload,
        agent_findings=decision_payload,
    )
    db.add(case)

    # Flush the parent case first so PostgreSQL can satisfy the
    # approvals.case_id foreign-key constraint in the same unit of work.
    # This does NOT commit the transaction; everything still rolls back
    # together if a later write fails.
    db.flush()

    if decision.transaction_score.requires_human_review:
        db.add(
            Approval(
                case_id=case.id,
                requested_role="fraud_analyst",
                requested_by_agent="multi_agent_orchestrator",
                status=ApprovalStatus.PENDING,
            )
        )

    # Persist the latest model outputs onto the transaction.
    transaction.fraud_probability = decision.transaction_score.fraud_probability
    transaction.anomaly_score = decision.transaction_score.anomaly_score

    if str(decision.decision).lower() == "block":
        transaction.status = TransactionStatus.BLOCKED
    elif decision.transaction_score.requires_human_review:
        transaction.status = TransactionStatus.REVIEW
    else:
        transaction.status = TransactionStatus.APPROVED

    # Keep the DB audit ID aligned with the orchestrator audit ID.
    db.add(
        AuditLog(
            id=UUID(str(decision.audit_id)),
            actor_type="agent",
            actor_id="multi_agent_orchestrator",
            action="fraud_investigation_completed",
            resource_type="transaction",
            resource_id=str(transaction.id),
            outcome="success",
            details={
                "initiated_by": principal_audit_details(
                    current_user
                ),
                "case_id": str(case.id),
                "decision": str(decision.decision),
                "risk_level": str(decision.transaction_score.risk_level),
                "risk_score": decision.transaction_score.combined_risk_score,
                "final_confidence": decision.final_confidence,
                "requires_human_review": (
                    decision.transaction_score.requires_human_review
                ),
                "agents": [
                    finding.get("agent")
                    for finding in decision_payload.get("findings", [])
                ],
            },
        )
    )

    _commit_or_rollback(db)
    return decision



# ============================================================
# LOAN APPLICATIONS
# ============================================================


@router.post(
    "/loans",
    response_model=LoanApplicationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_loan_application(
    current_user: CurrentUser,
    payload: LoanApplicationCreate,
    db: Session = Depends(get_db),
) -> LoanApplication:
    ensure_permission(current_user, Permission.PLATFORM_ADMIN)
    """Create a loan application linked to an existing customer."""

    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    loan = LoanApplication(
        external_id=payload.external_id,
        customer_id=payload.customer_id,
        requested_amount=payload.requested_amount,
        annual_income=payload.annual_income,
        debt_to_income_ratio=payload.debt_to_income_ratio,
        credit_score=payload.credit_score,
        risk_probability=payload.risk_probability,
        status=payload.status,
        decision_reason=payload.decision_reason,
    )

    db.add(loan)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Loan application with this external_id already exists.",
        ) from exc

    db.refresh(loan)
    return loan


@router.get(
    "/loans",
    response_model=list[LoanApplicationRead],
)
def list_loan_applications(
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[LoanApplication]:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Return loan applications using pagination."""

    statement = (
        select(LoanApplication)
        .order_by(LoanApplication.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get(
    "/loans/{loan_id}",
    response_model=LoanApplicationRead,
)
def get_loan_application(
    current_user: CurrentUser,
    loan_id: UUID,
    db: Session = Depends(get_db),
) -> LoanApplication:
    ensure_permission(current_user, Permission.BANKING_READ)
    """Retrieve one loan application by internal UUID."""

    loan = db.get(LoanApplication, loan_id)
    if loan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loan application not found.",
        )
    return loan


# ============================================================
# INVESTIGATION CASES
# ============================================================


@router.get(
    "/cases",
    response_model=list[InvestigationCaseRead],
)
def list_investigation_cases(
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[InvestigationCase]:
    ensure_permission(current_user, Permission.INVESTIGATION_READ)
    """Return persisted AI investigation cases."""

    statement = (
        select(InvestigationCase)
        .order_by(InvestigationCase.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get(
    "/cases/{case_id}",
    response_model=InvestigationCaseRead,
)
def get_investigation_case(
    current_user: CurrentUser,
    case_id: UUID,
    db: Session = Depends(get_db),
) -> InvestigationCase:
    ensure_permission(current_user, Permission.INVESTIGATION_READ)
    """Return one persisted AI investigation case."""

    case = db.get(InvestigationCase, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation case not found.",
        )
    return case


# ============================================================
# HUMAN APPROVALS
# ============================================================


@router.get(
    "/approvals",
    response_model=list[ApprovalRead],
)
def list_approvals(
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Approval]:
    ensure_permission(current_user, Permission.INVESTIGATION_READ)
    """Return human-review requests."""

    statement = (
        select(Approval)
        .order_by(Approval.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.patch(
    "/approvals/{approval_id}",
    response_model=ApprovalRead,
)
def review_approval(
    current_user: CurrentUser,
    approval_id: UUID,
    payload: ApprovalReviewRequest,
    db: Session = Depends(get_db),
) -> Approval:
    approval_for_auth = db.get(
        Approval,
        approval_id,
    )

    if approval_for_auth is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found.",
        )

    case_for_auth = db.get(
        InvestigationCase,
        approval_for_auth.case_id,
    )

    if case_for_auth is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation case not found.",
        )

    ensure_workflow_decision_permission(
        current_user,
        case_for_auth.case_type,
    )

    """Approve or reject a pending AI-generated review request."""

    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found.",
        )

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval request has already been decided.",
        )

    case = db.get(InvestigationCase, approval.case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation case linked to approval was not found.",
        )

    approval.status = (
        ApprovalStatus.APPROVED if payload.approved else ApprovalStatus.REJECTED
    )
    approval.reviewer_id = current_user.username
    approval.reviewer_comment = payload.reviewer_comment
    approval.decided_at = datetime.now(timezone.utc)

    case.status = (
        CaseStatus.RESOLVED if payload.approved else CaseStatus.ESCALATED
    )

    db.add(
        AuditLog(
            actor_type="human",
            actor_id=current_user.subject,
            action=(
                "investigation_approval_approved"
                if payload.approved
                else "investigation_approval_rejected"
            ),
            resource_type="investigation_case",
            resource_id=str(case.id),
            outcome="success",
            details={
                "authenticated_principal": principal_audit_details(
                    current_user
                ),
                "approval_id": str(approval.id),
                "reviewer_comment": payload.reviewer_comment,
                "new_case_status": case.status.value,
            },
        )
    )

    _commit_or_rollback(db)
    db.refresh(approval)
    return approval


# ============================================================
# AUDIT LOGS
# ============================================================


@router.get(
    "/audit-logs",
    response_model=list[AuditLogRead],
)
def list_audit_logs(
    current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    ensure_permission(current_user, Permission.AUDIT_READ)
    """Return persisted system, agent and human audit events."""

    statement = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())

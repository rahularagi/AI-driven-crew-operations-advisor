from fastapi import APIRouter, Body, HTTPException

from crew_ops_backend.services import disruption_service

router = APIRouter(prefix="/disruptions", tags=["Disruptions"])


@router.get("/proposals")
def get_proposals():
    return disruption_service.get_pending_proposals()


@router.post("/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: str, decided_by: str = Body(...)):
    result = disruption_service.accept_proposal(proposal_id, decided_by)
    if result is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return result


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: str,
    decided_by: str = Body(...),
    rejection_reason: str = Body(...),
):
    result = disruption_service.reject_proposal(proposal_id, decided_by, rejection_reason)
    if result is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return result

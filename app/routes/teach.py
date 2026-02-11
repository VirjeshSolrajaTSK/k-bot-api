"""Teach Mode routes."""
from typing import Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.sessions import get_db
from typing import Optional, Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.sessions import get_db
from app.core.security import get_current_user
from app.models import TeachingModule, TeachingConcept, TeachingSession
from app.services.teach_engine import TeachingEngine


router = APIRouter(prefix="", tags=["Teach"])

SESSION_NOT_FOUND = "Session not found"


class ModuleItem(BaseModel):
    id: str
    title: str
    description: Optional[str]
    sequence_order: int
    difficulty_level: Optional[str]

    class Config:
        orm_mode = True


class ModuleListResponse(BaseModel):
    modules: List[ModuleItem]


class StartSessionRequest(BaseModel):
    module_id: Optional[str] = None
    resume: Optional[bool] = True


class StartSessionResponse(BaseModel):
    session_id: str
    current_state: Dict[str, Any]


class Citation(BaseModel):
    chunk_id: str
    page: Optional[int]
    highlight: Optional[str]


class Option(BaseModel):
    key: str
    text: str


class Progress(BaseModel):
    module: float
    overall: float


class InteractionResponse(BaseModel):
    type: str
    content: Optional[str] = None
    citations: Optional[List[Citation]] = []
    options: Optional[List[Option]] = []
    is_checkpoint: Optional[bool] = False
    progress: Optional[Progress] = None
    next: Optional[Dict[str, Any]] = None


class InteractRequest(BaseModel):
    choice: Optional[str] = None
    question: Optional[str] = None


class SessionStatusResponse(BaseModel):
    session_id: str
    current_state: Dict[str, Any]
    progress: float


class NavigateRequest(BaseModel):
    action: str  # 'skip'|'back'|'jump_to_module'
    target: Optional[str] = None


class NavigateResponse(BaseModel):
    status: str
    session_state: Dict[str, Any]


@router.get("/kb/{kb_id}/teach/modules", response_model=ModuleListResponse)
def list_modules(kb_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    modules = db.query(TeachingModule).filter(TeachingModule.kb_id == kb_id).order_by(TeachingModule.sequence_order).all()
    modules_data = []
    for m in modules:
        modules_data.append({
            "id": str(m.id),
            "title": m.title,
            "description": m.description,
            "sequence_order": m.sequence_order,
            "difficulty_level": m.difficulty_level,
        })
    return {"modules": modules_data}


@router.post("/teach/{kb_id}/start", response_model=StartSessionResponse)
def start_teach_session(kb_id: str, body: StartSessionRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    engine = TeachingEngine(db)
    session = engine.start_session(kb_id=kb_id, user_id=current_user.id, module_id=body.module_id, resume=body.resume)
    return StartSessionResponse(session_id=str(session.id), current_state=session.session_state or {})


@router.post("/teach/session/{session_id}/interact", response_model=InteractionResponse)
def interact(session_id: str, body: InteractRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # verify ownership
    session = db.query(TeachingSession).filter(TeachingSession.id == session_id, TeachingSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_NOT_FOUND)

    engine = TeachingEngine(db)
    resp = engine.process_interaction(session_id=session_id, payload=body.dict())
    # coerce resp dict into InteractionResponse (Pydantic will validate)
    return InteractionResponse(**resp)


@router.get("/teach/session/{session_id}/status", response_model=SessionStatusResponse)
def session_status(session_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    session = db.query(TeachingSession).filter(TeachingSession.id == session_id, TeachingSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_NOT_FOUND)
    return SessionStatusResponse(session_id=str(session.id), current_state=session.session_state or {}, progress=float(session.progress_percentage or 0))


@router.post("/teach/session/{session_id}/navigate", response_model=NavigateResponse)
def navigate(session_id: str, body: NavigateRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Simple navigation handler: maps actions to engine interactions
    session = db.query(TeachingSession).filter(TeachingSession.id == session_id, TeachingSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_NOT_FOUND)

    engine = TeachingEngine(db)
    action = body.action
    if action == "skip":
        engine.process_interaction(session_id=session_id, payload={"choice": "continue"})
        return NavigateResponse(status="ok", session_state=session.session_state or {})
    if action == "back":
        # naive: re-show current content
        engine.process_interaction(session_id=session_id, payload={})
        return NavigateResponse(status="ok", session_state=session.session_state or {})
    if action == "jump_to_module" and body.target:
        # set current module and concept to target module
        session.current_module_id = body.target
        first = db.query(TeachingConcept).filter(TeachingConcept.module_id == body.target).order_by(TeachingConcept.created_at).first()
        session.current_concept_id = first.id if first else None
        db.commit()
        return NavigateResponse(status="ok", session_state=session.session_state or {})

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid navigation action")

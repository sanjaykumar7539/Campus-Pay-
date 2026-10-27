"""Paid-receipt queue for a station-scoped native printer service."""
import secrets
from datetime import timedelta
from sqlalchemy import select, update
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict
from typing import Literal
from modules.auth.kiosk_models import PrinterAgent, PrintJob
from modules.payments.models import Receipt, Payment
from modules.audit import service as audit
from app import kiosk_service as kiosk
from app.kiosk_router import kiosk as station
from core.security import get_db, tenant_db, require_roles
from core.errors import ForbiddenError, ConflictError, NotFoundError, UnauthorizedError, ok
from shared.clock import utcnow
router=APIRouter(prefix='/api/v1',tags=['native-printing'])

def agent(x_printer_token: str=Header(default=''),db=Depends(get_db)):
    a=db.execute(select(PrinterAgent).where(PrinterAgent.token_hash==kiosk.digest(x_printer_token))).scalar_one_or_none()
    if not a:raise UnauthorizedError('Printer credentials rejected')
    kiosk.active_device(db,a.institution_id,a.device_id)
    return a

def output(job):
    return {'id':job.id,'state':job.state,'checkout_id':job.checkout_id}

def job_for(db,a,jid):
    job=db.execute(select(PrintJob).where(PrintJob.id==jid,PrintJob.institution_id==a.institution_id,
        PrintJob.device_id==a.device_id).with_for_update()).scalar_one_or_none()
    if not job:raise NotFoundError('Print job not found')
    return job

@router.post('/admin/devices/{device_id}/printer-key')
def provision(device_id: str,p=Depends(require_roles('ADMIN')),db=Depends(tenant_db)):
    kiosk.active_device(db,p.institution_id,device_id)
    row=db.execute(select(PrinterAgent).where(PrinterAgent.device_id==device_id,
        PrinterAgent.institution_id==p.institution_id)).scalar_one_or_none()
    token=secrets.token_urlsafe(48)
    if row:row.token_hash,row.last_seen_at=kiosk.digest(token),None
    else:db.add(PrinterAgent(institution_id=p.institution_id,device_id=device_id,token_hash=kiosk.digest(token)))
    db.execute(update(PrintJob).where(PrintJob.device_id==device_id,PrintJob.institution_id==p.institution_id,
        PrintJob.state=='QUEUED').values(state='CANCELLED'))
    audit.record_event(db,institution_id=p.institution_id,actor_id=p.user_id,actor_role='ADMIN',
        event_type='PRINTER_KEY_ROTATED',entity_type='Device',entity_id=device_id)
    db.commit();return ok({'printer_token':token})

@router.get('/admin/devices/{device_id}/hardware')
def hardware(device_id: str,p=Depends(require_roles('ADMIN')),db=Depends(tenant_db)):
    kiosk.active_device(db,p.institution_id,device_id)
    a=db.execute(select(PrinterAgent).where(PrinterAgent.device_id==device_id,
        PrinterAgent.institution_id==p.institution_id)).scalar_one_or_none()
    return ok({'printer_online':bool(a and a.last_seen_at and a.last_seen_at>utcnow()-timedelta(seconds=30)),
        'scanner_online':kiosk.scanner_online(db,device_id),
        'morpho_matching':'Requires vendor E2 MSO SDK adapter; RD app is not student matching'})

@router.post('/kiosk/checkouts/{cid}/print')
def enqueue(cid: str,s=Depends(station),db=Depends(get_db)):
    kiosk.active_device(db,s.institution_id,s.device_id)
    c=kiosk.kiosk_challenge(db,s,cid)
    if c.status!='CONSUMED' or not c.order_id:raise ForbiddenError('Only a paid active checkout can be printed')
    prior=db.execute(select(PrintJob).where(PrintJob.checkout_id==cid)).scalar_one_or_none()
    if prior:return ok(output(prior))
    a=db.execute(select(PrinterAgent).where(PrinterAgent.device_id==s.device_id,
        PrinterAgent.institution_id==s.institution_id)).scalar_one_or_none()
    if not a or not a.last_seen_at or a.last_seen_at<=utcnow()-timedelta(seconds=30):
        raise ConflictError('Thermal printer service offline. Receipt retained; no further payment is required.',code='PRINTER_OFFLINE')
    receipt=db.execute(select(Receipt).join(Payment,Receipt.payment_id==Payment.id).where(
        Receipt.institution_id==s.institution_id,Payment.order_id==c.order_id,Payment.status=='COMPLETED')).scalar_one_or_none()
    if not receipt:raise ConflictError('Paid receipt unavailable; ask staff for reprint')
    job=PrintJob(institution_id=s.institution_id,device_id=s.device_id,checkout_id=cid,snapshot={**receipt.snapshot,"receipt_number":receipt.receipt_number})
    db.add(job);db.commit();return ok(output(job))

@router.get('/kiosk/checkouts/{cid}/print')
def status(cid: str,s=Depends(station),db=Depends(get_db)):
    c=kiosk.kiosk_challenge(db,s,cid)
    job=db.execute(select(PrintJob).where(PrintJob.checkout_id==c.id)).scalar_one_or_none()
    if not job:raise NotFoundError('No print job')
    if job.state=='CLAIMED' and job.claimed_at<=utcnow()-timedelta(seconds=90):
        job.state='UNKNOWN';db.commit()
    return ok(output(job))

@router.get('/printer/jobs')
def jobs(a=Depends(agent),db=Depends(get_db)):
    a.last_seen_at=utcnow()
    db.execute(update(PrintJob).where(PrintJob.device_id==a.device_id,PrintJob.institution_id==a.institution_id,
        PrintJob.state=='QUEUED',PrintJob.created_at<=utcnow()-timedelta(seconds=90)).values(state='CANCELLED'))
    db.execute(update(PrintJob).where(PrintJob.device_id==a.device_id,PrintJob.institution_id==a.institution_id,
        PrintJob.state=='CLAIMED',PrintJob.claimed_at<=utcnow()-timedelta(seconds=90)).values(state='UNKNOWN'))
    rows=db.execute(select(PrintJob).where(PrintJob.device_id==a.device_id,PrintJob.institution_id==a.institution_id,
        PrintJob.state=='QUEUED').order_by(PrintJob.created_at).limit(1)).scalars().all()
    db.commit();return ok([output(j) for j in rows])

@router.post('/printer/jobs/{jid}/claim')
def claim(jid: str,a=Depends(agent),db=Depends(get_db)):
    kiosk.active_device(db,a.institution_id,a.device_id)
    j=job_for(db,a,jid)
    if j.state!='QUEUED' or j.created_at<=utcnow()-timedelta(seconds=90):raise ConflictError('Job already claimed; do not print again')
    j.state='CLAIMED';j.claimed_at=utcnow();db.commit()
    return ok({**output(j),'receipt':j.snapshot})

class Result(BaseModel):
    model_config=ConfigDict(extra='forbid')
    state: Literal['SUBMITTED','FAILED','UNKNOWN']

@router.post('/printer/jobs/{jid}/result')
def result(jid: str,body: Result,a=Depends(agent),db=Depends(get_db)):
    kiosk.active_device(db,a.institution_id,a.device_id)
    j=job_for(db,a,jid)
    if j.state==body.state:return ok(output(j))
    if j.state!='CLAIMED':raise ConflictError('Print result cannot overwrite final job state')
    j.state=body.state
    audit.record_event(db,institution_id=a.institution_id,actor_id=a.device_id,actor_role='PRINTER',
        event_type='PRINT_'+j.state,entity_type='PrintJob',entity_id=j.id)
    db.commit();return ok(output(j))

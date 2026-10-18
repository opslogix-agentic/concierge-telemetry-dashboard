from collections import defaultdict
from datetime import datetime,timezone
import logging
from django.contrib.auth.decorators import login_required
from django.http import Http404,JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from . import data
logger=logging.getLogger(__name__)

def healthz(request):
    return JsonResponse({"status":"ok","service":"concierge-telemetry-dashboard"})

def load():
    items=data.devices();error=None
    try:alerts=data.alert_rows()
    except Exception:
        logger.exception("Icinga state read failed");alerts=[];error="Icinga alert data is unavailable. Alert status is UNKNOWN, not healthy."
    return data.attach_alerts(items,alerts),error

@login_required
@never_cache
@require_GET
def overview(request,category="locations"):
    try:items,error=load()
    except Exception:
        logger.exception("Inventory read failed")
        return render(request,"inventory/error.html",status=503)
    items=[d for d in items if bool(d.get("meraki_integration_id")) == (category=="meraki")]
    locations=sorted({d["location_name"] for d in items});query=request.GET.get("q","").strip();location=request.GET.get("location","");status=request.GET.get("status","")
    totals={"devices":len(items),"locations":len(locations),"problems":sum(d["alert_status"] in {"CRITICAL","WARNING"} for d in items),"unknown":sum(d["alert_status"]=="UNKNOWN" for d in items)}
    filtered=[d for d in items if (not location or d["location_name"]==location) and (not status or d["alert_status"]==status) and (not query or query.casefold() in " ".join(str(d.get(k) or "") for k in ["hostname","display_name","management_ip","model","serial_number","collector"]).casefold())]
    grouped=defaultdict(list)
    for d in filtered:grouped[d["location_name"]].append(d)
    summaries=[{"name":loc,"count":sum(d["location_name"]==loc for d in filtered),"problems":sum(d["location_name"]==loc and d["alert_status"] in {"WARNING","CRITICAL"} for d in filtered)} for loc in sorted(grouped)]
    browse=not (location or query or status)
    return render(request,"inventory/overview.html",{"groups":{} if browse else dict(grouped),"browse":browse,"summaries":summaries,"category":category,"title":"Meraki" if category=="meraki" else "CP Locations","locations":locations,"totals":totals,"query":query,"location":location,"status_filter":status,"error":error,"now":datetime.now(timezone.utc),"shown":len(filtered),"meraki_health":data.integration_health() if category=="meraki" else []})

@login_required
@never_cache
@require_GET
def device(request,device_id):
    try:items,error=load()
    except Exception:
        logger.exception("Inventory read failed");return render(request,"inventory/error.html",status=503)
    d=next((d for d in items if d["id"]==device_id),None)
    if d is None:raise Http404("Device not found")
    try:tables=[] if d.get("meraki_integration_id") and not d.get("local_polling_enabled",True) else data.tables(device_id)
    except Exception:
        logger.exception("Device inventory read failed");return render(request,"inventory/error.html",status=503)
    metadata=[(k.replace("_"," ").title(),v) for k,v in d.items() if k not in {"alerts","problem_count","alert_status","telemetry_stale","id","location_id","assigned_appliance_id","last_collected_by_appliance_id","tenant_uuid","location_uuid","meraki_integration_id","meraki_serial","meraki_collected_at","display_name"}]
    return render(request,"inventory/device.html",{"device":d,"metadata":metadata,"tables":tables,"health":data.health(d),"error":error})

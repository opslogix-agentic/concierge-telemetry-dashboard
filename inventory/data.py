"""SELECT-only access to existing inventory and persisted Icinga states."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from django.conf import settings
from django.db import connections

LABELS = {0:"OK",1:"WARNING",2:"CRITICAL",3:"UNKNOWN"}
RANK = {"OK":0,"UNKNOWN":1,"WARNING":2,"CRITICAL":3}

def rows(alias, sql, params=()):
    if not sql.lstrip().upper().startswith("SELECT "):
        raise ValueError("Inventory connections only support SELECT")
    with connections[alias].cursor() as c:
        c.execute(sql, params)
        return [dict(zip([x[0] for x in c.description],r)) for r in c.fetchall()]

def name_meraki_devices(items):
    """Readable monitoring aliases; physical database identities remain stable."""
    groups={}
    for item in items:
        if item.get("meraki_integration_id"):
            slug=lambda value: re.sub(r"[^a-z0-9]+","-",str(value).lower()).strip("-")
            base="meraki-"+slug(item["location_name"])+"-"+slug(item.get("model") or item.get("device_role") or "device")
            groups.setdefault(base,[]).append(item)
    for base,members in groups.items():
        for index,item in enumerate(sorted(members,key=lambda x:x["hostname"]),1):
            item["monitoring_name"]=base+(f"-{index:02d}" if len(members)>1 else "")
    aliases=json.loads(Path(__file__).with_name("meraki_monitoring_aliases.json").read_text())
    for item in items:
        if item["hostname"] in aliases:item["monitoring_name"]=aliases[item["hostname"]]
    return items

def devices():
    items = rows("telemetry", """SELECT d.*,mi.integration_id AS meraki_integration_id,mi.serial AS meraki_serial,mh.collected_at AS meraki_collected_at,l.name AS location_name,l.location_uuid,t.name AS tenant_name,t.tenant_uuid,a.appliance_id AS collector,
    (SELECT COUNT(*) FROM network_interfaces i WHERE i.device_id=d.id AND i.enabled=1) AS interface_count,
    (SELECT COUNT(*) FROM network_device_stack_members m WHERE m.device_id=d.id AND m.enabled=1) AS member_count
    FROM network_devices d JOIN locations l ON l.id=d.location_id JOIN tenants t ON t.id=l.tenant_id LEFT JOIN appliances a ON a.id=d.assigned_appliance_id LEFT JOIN meraki_device_identities mi ON mi.device_id=d.id LEFT JOIN meraki_health_snapshots mh ON mh.integration_id=mi.integration_id AND mh.resource=IF(d.device_role='sensor','sensors','availability') WHERE t.tenant_uuid=%s ORDER BY l.name,d.hostname""",(settings.TENANT_UUID,))
    snapshots=rows("telemetry","""SELECT s.snapshot_json FROM meraki_discovery_snapshots s
        JOIN meraki_integrations i ON i.id=s.integration_id JOIN tenants t ON t.id=i.tenant_id
        WHERE t.tenant_uuid=%s""",(settings.TENANT_UUID,))
    names={x["serial"]:x["name"] for row in snapshots for x in json.loads(row["snapshot_json"]).get("devices",[])}
    for item in items:
        item["display_name"]=names.get(item.get("meraki_serial"),item["hostname"])
        item["telemetry_source"]="Meraki cloud" if item.get("meraki_integration_id") else "Client collector"
    return name_meraki_devices(items)

def alert_rows():
    service = rows("icinga", """SELECT h.name AS hostname,s.name AS name,ss.soft_state AS code,ss.hard_state AS hard_code,ss.state_type,ss.output,ss.last_update,ss.is_overdue,ss.is_acknowledged,ss.in_downtime FROM host h JOIN service s ON s.host_id=h.id LEFT JOIN service_state ss ON ss.service_id=s.id""")
    host = rows("icinga", """SELECT h.name AS hostname,'Host reachability' AS name,hs.soft_state AS code,hs.hard_state AS hard_code,hs.state_type,hs.output,hs.last_update,hs.is_overdue,hs.is_acknowledged,hs.in_downtime FROM host h LEFT JOIN host_state hs ON hs.host_id=h.id""")
    for a in service+host:
        host_check=a["name"]=="Host reachability"
        a["status"] = ("OK" if a["code"]==0 else "CRITICAL" if a["code"] is not None else "UNKNOWN") if host_check else LABELS.get(a["code"],"UNKNOWN")
        a["hard_status"] = ("OK" if a["hard_code"]==0 else "CRITICAL" if a["hard_code"] is not None else "UNKNOWN") if host_check else LABELS.get(a["hard_code"],"UNKNOWN")
        a["updated"] = datetime.fromtimestamp(a["last_update"]/1000,timezone.utc) if a["last_update"] else None
        if a["code"] is None:a["status"]="UNKNOWN";a["output"]="No check result recorded"
        a["overdue"] = a["is_overdue"]=="y"
    return service+host

def health_timestamp(device):
    if device.get("meraki_integration_id"):
        dt=device.get("meraki_collected_at")
        return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt
    parts=[device.get("tenant_uuid",""),device.get("location_uuid",""),device["hostname"].lower()]
    if not all(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*",str(p)) for p in parts):return None
    path=Path(settings.STATE_ROOT)/"tenants"/parts[0]/"locations"/parts[1]/"network"/parts[2]/"health.json"
    try:
        document=json.loads(path.read_text())
        dt=datetime.fromisoformat(document["collected_at"].replace("Z","+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except (OSError,ValueError,KeyError,TypeError):return None

def attach_alerts(items, alerts):
    by_host={}
    for a in alerts:by_host.setdefault(a["hostname"].casefold(),[]).append(a)
    for d in items:
        d["alerts"] = sorted(by_host.get(d.get("monitoring_name",d["hostname"]).casefold(),by_host.get(d["hostname"].casefold(),[])),key=lambda a:(-RANK[a["status"]],a["name"]))
        if d.get("meraki_integration_id"):
            for alert in d["alerts"]:
                if alert["name"]=="Host reachability":alert["name"]="Cloud monitoring anchor"
        d["alert_status"] = max((a["status"] for a in d["alerts"]),key=lambda s:RANK[s],default="UNKNOWN")
        d["problem_count"] = sum(a["status"]!="OK" for a in d["alerts"])
        d["inventory_collected_at"] = d.get("telemetry_collected_at")
        # SQL marker advances on hourly inventory; freshness must use fast health.
        d["telemetry_collected_at"] = health_timestamp(d)
        dt=d["telemetry_collected_at"]
        d["telemetry_stale"] = dt is None or (datetime.now(timezone.utc)-dt).total_seconds()>settings.TELEMETRY_STALE_SECONDS
    return items

def tables(device_id):
    specs = [
      ("Interfaces", "SELECT i.* FROM network_interfaces i WHERE i.device_id=%s ORDER BY i.name"),
      ("Interface addresses", "SELECT i.name AS interface_name,p.address,p.prefix_length FROM network_interface_ip_addresses p JOIN network_interfaces i ON i.id=p.interface_id WHERE i.device_id=%s ORDER BY i.name,p.address"),
      ("Allowed VLANs", "SELECT i.name AS interface_name,v.vlan_id FROM network_interface_allowed_vlans v JOIN network_interfaces i ON i.id=v.interface_id WHERE i.device_id=%s ORDER BY i.name,v.vlan_id"),
      ("Stack members", "SELECT m.* FROM network_device_stack_members m WHERE m.device_id=%s ORDER BY m.member_id"),
      ("Power supplies (inventory)", "SELECT m.member_id,p.* FROM network_device_power_supplies p JOIN network_device_stack_members m ON m.id=p.stack_member_id WHERE m.device_id=%s ORDER BY m.member_id,p.slot"),
      ("Fans (inventory)", "SELECT m.member_id,f.* FROM network_device_fans f JOIN network_device_stack_members m ON m.id=f.stack_member_id WHERE m.device_id=%s ORDER BY m.member_id,f.fan_id"),
      ("Temperature sensors (inventory)", "SELECT m.member_id,s.* FROM network_device_temperature_sensors s JOIN network_device_stack_members m ON m.id=s.stack_member_id WHERE m.device_id=%s ORDER BY m.member_id,s.name"),
    ]
    result=[]
    hidden={"id","device_id","stack_member_id","first_seen_at"}
    for title,sql in specs:
        records=rows("telemetry",sql,(device_id,))
        keys=[k for k in records[0] if k not in hidden] if records else []
        result.append({"title":title,"columns":[k.replace("_"," ").title() for k in keys],"rows":[[r[k] for k in keys] for r in records],"count":len(records)})
    return result

def health(device):
    meraki=bool(device.get("meraki_integration_id"))
    resources=(["sensor-freshness","temperature","battery"] if device.get("device_role")=="sensor" else ["availability"]) if meraki else ["cpu","memory","temperature","fans","power"]
    kind="meraki" if meraki else "network"
    try:token=Path(settings.MONITOR_TOKEN_FILE).read_text().strip()
    except OSError:return [{"resource":r,"status":"UNKNOWN","message":"Controller health credential is unavailable"} for r in resources]
    scope=urlencode({"tenant_uuid":device["tenant_uuid"],"location_uuid":device["location_uuid"]})
    def get(resource):
        url=settings.CONTROLLER_URL+"/api/v1/health/"+kind+"/"+quote(device["hostname"],safe="")+"/"+resource+"?"+scope
        try:
            with urlopen(Request(url,headers={"Authorization":"Bearer "+token}),timeout=4) as response:d=json.load(response)
            return {"resource":resource,"status":d.get("status","UNKNOWN"),"message":"; ".join(x.get("message","") for x in d.get("checks",{}).values()),"details":json.dumps(d.get("details",[]),indent=2),"age":d.get("age_seconds")}
        except Exception:return {"resource":resource,"status":"UNKNOWN","message":"Live controller health is unavailable"}
    with ThreadPoolExecutor(max_workers=5) as pool:return list(pool.map(get,resources))


def integration_health():
    """Read scoped controller state only; no vendor credentials or vendor requests."""
    try:
        integrations=rows("telemetry","""SELECT i.id,i.organization_id,l.location_uuid,t.tenant_uuid
            FROM meraki_integrations i JOIN appliances a ON a.id=i.assigned_appliance_id
            JOIN locations l ON l.id=a.location_id JOIN tenants t ON t.id=i.tenant_id
            WHERE t.tenant_uuid=%s AND i.enabled=TRUE""",(settings.TENANT_UUID,))
        token=Path(settings.MONITOR_TOKEN_FILE).read_text().strip()
    except Exception:return [{"organization":"Meraki","resource":"source","status":"UNKNOWN","message":"Meraki integration health is unavailable"}]
    cards=[]
    for integration in integrations:
        query=urlencode({"tenant_uuid":integration["tenant_uuid"],"location_uuid":integration["location_uuid"]})
        for resource in ["source","licensing"]:
            card={"organization":integration["organization_id"],"resource":resource,"status":"UNKNOWN","message":"Controller health unavailable"}
            try:
                url=settings.CONTROLLER_URL+"/api/v1/health/meraki/integration-"+str(integration["id"])+"/"+resource+"?"+query
                with urlopen(Request(url,headers={"Authorization":"Bearer "+token}),timeout=4) as response:body=json.load(response)
                card.update(status=body["status"],message="; ".join(x["message"] for x in body["checks"].values()))
            except Exception:pass
            cards.append(card)
    return cards

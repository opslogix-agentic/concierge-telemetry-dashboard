#!/usr/bin/env python3
"""Install from the already-pulled repository as root. Never edits application source."""
import os,json,secrets,subprocess,shutil,pwd,shlex
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parent.parent
assert os.geteuid()==0,"Run installer as root"
assert str(ROOT)=="/opt/telemetry/concierge-telemetry-dashboard","Install from the production checkout"
CONFIG=Path("/etc/concierge-telemetry-dashboard")
CONFIG.mkdir(mode=0o750,exist_ok=True)
u=pwd.getpwnam("telemetry");os.chown(CONFIG,0,u.pw_gid)
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def sql(s):run(["sudo","-n","-u","mysql","mariadb"],input=s,text=True,stdout=subprocess.DEVNULL)
env_file=CONFIG/"dashboard.env"
if not env_file.exists():
 env={"DJANGO_SECRET_KEY":secrets.token_urlsafe(64),"DJANGO_ALLOWED_HOSTS":"localhost,127.0.0.1,10.1.96.3,10.20.20.9,10.100.20.1,10.200.20.1,concierge-controller,chcnc-mon","DASHBOARD_DB_USER":"concierge_dashboard","DASHBOARD_DB_PASSWORD":secrets.token_urlsafe(32),"INVENTORY_DB_USER":"concierge_inventory","INVENTORY_DB_PASSWORD":secrets.token_urlsafe(32)}
 sql("CREATE DATABASE IF NOT EXISTS concierge_dashboard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
 for prefix in ["DASHBOARD_DB","INVENTORY_DB"]:
  sql("CREATE USER IF NOT EXISTS '"+env[prefix+"_USER"]+"'@'127.0.0.1' IDENTIFIED BY '"+env[prefix+"_PASSWORD"]+"'; ALTER USER '"+env[prefix+"_USER"]+"'@'127.0.0.1' IDENTIFIED BY '"+env[prefix+"_PASSWORD"]+"';")
 sql("GRANT ALL PRIVILEGES ON concierge_dashboard.* TO 'concierge_dashboard'@'127.0.0.1'; GRANT SELECT ON prod_telemetry.* TO 'concierge_inventory'@'127.0.0.1';")
 for table in ["host","host_state","service","service_state"]:sql("GRANT SELECT ON icingadb."+table+" TO 'concierge_inventory'@'127.0.0.1';")
 env_file.write_text("".join(k+"="+json.dumps(v)+"\n" for k,v in env.items()));env_file.chmod(0o640);os.chown(env_file,0,u.pw_gid)
else:env={k:shlex.split(v)[0] for k,v in (l.split("=",1) for l in env_file.read_text().splitlines() if l and not l.startswith("#"))}
monitor=CONFIG/"monitor.token"
if not monitor.exists():shutil.copyfile("/etc/icinga2/secrets/telemetry-api.token",monitor)
monitor.chmod(0o640);os.chown(monitor,0,u.pw_gid)
python="/opt/telemetry/dashboard-venv/bin/python"
process_env={**os.environ,**env}
def django(*args):run(["sudo","-n","-u","telemetry","-H","--preserve-env=DJANGO_SECRET_KEY,DJANGO_ALLOWED_HOSTS,DASHBOARD_DB_USER,DASHBOARD_DB_PASSWORD,INVENTORY_DB_USER,INVENTORY_DB_PASSWORD",python,"manage.py",*args],cwd=ROOT,env=process_env)
django("check")
django("migrate","--noinput","--database=default")
django("collectstatic","--noinput")
bootstrap=CONFIG/"bootstrap-admin.json"
if not bootstrap.exists():
 credential={"username":"cchavez","password":secrets.token_urlsafe(24)}
 code="from django.contrib.auth import get_user_model; import json; c=json.loads(input()); U=get_user_model(); assert not U.objects.filter(username=c['username']).exists(), 'Existing user: refusing password reset'; U.objects.create_superuser(c['username'],'cchavez@opslogix.io',c['password']); print('Initial dashboard administrator created')"
 run([python,"manage.py","shell","-c",code],cwd=ROOT,env=process_env,input=json.dumps(credential),text=True)
 bootstrap.write_text(json.dumps(credential));bootstrap.chmod(0o600)
backup=Path("/var/backups/concierge-dashboard")/datetime.now().strftime("%Y%m%d-%H%M%S");backup.mkdir(parents=True,mode=0o700)
files={"concierge-telemetry-dashboard.service":"/etc/systemd/system/concierge-telemetry-dashboard.service","haproxy-dashboard.cfg":"/etc/haproxy/concierge-dashboard.cfg","haproxy-dashboard.conf":"/etc/systemd/system/haproxy.service.d/concierge-dashboard.conf","apache-dashboard.conf":"/etc/apache2/conf-available/concierge-dashboard.conf"}
for source,destination in files.items():
 dest=Path(destination);dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists():shutil.copy2(dest,backup/(source+".previous"))
 shutil.copy2(ROOT/"deploy"/source,dest);dest.chmod(0o644)
run(["haproxy","-c","-f","/etc/haproxy/haproxy.cfg","-f","/etc/haproxy/concierge-dashboard.cfg"])
run(["a2enmod","proxy","proxy_http"])
run(["a2enconf","concierge-dashboard"])
run(["apache2ctl","configtest"])
run(["systemctl","daemon-reload"])
run(["systemctl","enable","--now","concierge-telemetry-dashboard"])
run(["systemctl","restart","concierge-telemetry-dashboard"])
run(["systemctl","restart","haproxy"])
run(["systemctl","reload","apache2"])
print("Dashboard installed; bootstrap credentials stored in root-only configuration file; backup:",backup)

from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from django.test import TestCase,SimpleTestCase,Client
from django.contrib.auth import get_user_model
from . import data
from dashboard.router import ReadOnlyRouter

def sample():
 return {"id":1,"hostname":"CHC-SW-01-01","management_ip":"10.144.2.1","location_name":"Canton","model":"C9300","device_role":"switch","collector":"cp-concierge-collector","interface_count":2,"member_count":1,"enabled":1,"telemetry_collected_at":datetime.now(timezone.utc)}

def alert(status="CRITICAL"):
 return {"hostname":"chc-sw-01-01","name":"power","status":status,"hard_status":status,"state_type":"hard","output":"No Input Power","updated":datetime.now(timezone.utc),"overdue":False}

class StateTests(SimpleTestCase):
 def test_no_results_is_unknown(self):
  self.assertEqual(data.attach_alerts([sample()],[])[0]["alert_status"],"UNKNOWN")
 def test_critical_outweighs_unknown_and_case_matches(self):
  d=data.attach_alerts([sample()],[alert("UNKNOWN"),alert()])[0]
  self.assertEqual(d["alert_status"],"CRITICAL");self.assertEqual(d["problem_count"],2)
 def test_stale_and_never_collected(self):
  d=sample();d["telemetry_collected_at"]=datetime.now(timezone.utc)-timedelta(hours=1)
  self.assertTrue(data.attach_alerts([d],[])[0]["telemetry_stale"])
  d["telemetry_collected_at"]=None;self.assertTrue(data.attach_alerts([d],[])[0]["telemetry_stale"])
 @patch("inventory.data.health_timestamp",return_value=datetime.now(timezone.utc))
 def test_fresh_health_overrides_old_inventory_marker(self,_):
  d=sample();d["telemetry_collected_at"]=datetime.now(timezone.utc)-timedelta(hours=1)
  result=data.attach_alerts([d],[])[0];self.assertFalse(result["telemetry_stale"]);self.assertIsNotNone(result["inventory_collected_at"])
 def test_health_path_rejects_traversal(self):
  d=sample();d.update(tenant_uuid="tenant",location_uuid="location",hostname="../host")
  self.assertIsNone(data.health_timestamp(d))
 def test_write_query_rejected_before_db_access(self):
  with self.assertRaises(ValueError):data.rows("telemetry","DELETE FROM network_devices")
 def test_migrations_restricted_to_app_database(self):
  self.assertFalse(ReadOnlyRouter().allow_migrate("telemetry","auth"));self.assertFalse(ReadOnlyRouter().allow_migrate("icinga","auth"));self.assertTrue(ReadOnlyRouter().allow_migrate("default","auth"))
 @patch("inventory.data.rows")
 def test_host_down_is_critical_and_missing_service_unknown(self,rows):
  base={"hostname":"host","hard_code":1,"state_type":"hard","output":"down","last_update":None,"is_overdue":"n","is_acknowledged":"n","in_downtime":"n"}
  rows.side_effect=[[dict(base,name="power",code=None)],[dict(base,name="Host reachability",code=1)]]
  result=data.alert_rows();self.assertEqual(result[0]["status"],"UNKNOWN");self.assertEqual(result[1]["status"],"CRITICAL")
 @patch("inventory.data.Path.read_text",side_effect=OSError)
 def test_missing_controller_token_is_unknown(self,_):
  self.assertTrue(all(x["status"]=="UNKNOWN" for x in data.health(sample())))

class PageTests(TestCase):
 def setUp(self):
  mock=patch("inventory.views.data.integration_health",return_value=[]);mock.start();self.addCleanup(mock.stop)
  self.user=get_user_model().objects.create_user(username="operator",password="password-test")
 def test_login_required_for_inventory(self):
  self.assertEqual(self.client.get("/telemetry/").status_code,302);self.assertEqual(self.client.get("/telemetry/devices/1/").status_code,302)
 def test_healthcheck_does_not_disclose_inventory(self):
  self.assertEqual(self.client.get("/telemetry/healthz/").json()["status"],"ok")
 @patch("inventory.views.data.alert_rows",return_value=[alert()])
 @patch("inventory.views.data.devices",side_effect=lambda:[sample()])
 def test_location_card_and_filters(self,devices,alerts):
  self.client.force_login(self.user)
  response=self.client.get("/telemetry/?location=Canton");self.assertContains(response,"Canton");self.assertContains(response,"CRITICAL");self.assertContains(response,"CHC-SW-01-01")
  self.assertContains(self.client.get("/telemetry/?location=Malone"),"No devices match")
 @patch("inventory.views.data.alert_rows",side_effect=RuntimeError)
 @patch("inventory.views.data.devices",side_effect=lambda:[sample()])
 def test_icinga_outage_is_explicit_unknown(self,*_):
  self.client.force_login(self.user);response=self.client.get("/telemetry/");self.assertContains(response,"Icinga alert data is unavailable");self.assertContains(response,"UNKNOWN")
 @patch("inventory.views.data.devices",side_effect=RuntimeError)
 def test_inventory_outage_is_503(self,_):
  self.client.force_login(self.user);self.assertEqual(self.client.get("/telemetry/").status_code,503)
 @patch("inventory.views.data.health",return_value=[])
 @patch("inventory.views.data.tables",return_value=[])
 @patch("inventory.views.data.alert_rows",return_value=[dict(alert(),output="<script>bad()</script>")])
 @patch("inventory.views.data.devices",side_effect=lambda:[sample()])
 def test_detail_escapes_check_output_and_unknown_device_404(self,*_):
  self.client.force_login(self.user);response=self.client.get("/telemetry/devices/1/")
  self.assertContains(response,"&lt;script&gt;bad()");self.assertNotContains(response,"<script>bad()")
  self.assertEqual(self.client.get("/telemetry/devices/2/").status_code,404)
 def test_logout_requires_post(self):
  self.client.force_login(self.user);self.assertEqual(self.client.get("/telemetry/logout/").status_code,405)
 def test_login_csrf_required(self):
  c=Client(enforce_csrf_checks=True);self.assertEqual(c.post("/telemetry/login/",{"username":"operator","password":"password-test"}).status_code,403)


class UserManagementTests(TestCase):
 def setUp(self):
  U=get_user_model()
  self.admin=U.objects.create_superuser(username="administrator",password="AdminTest-42!long")
  self.viewer=U.objects.create_user(username="viewer",password="ViewerTest-42!long")
 def test_admin_can_create_regular_viewer(self):
  self.client.force_login(self.admin)
  response=self.client.post("/telemetry/admin/auth/user/add/",{"username":"newviewer","usable_password":"true","password1":"Distinct-Viewer-Pass!482","password2":"Distinct-Viewer-Pass!482","_save":"Save"})
  self.assertEqual(response.status_code,302)
  user=get_user_model().objects.get(username="newviewer")
  self.assertTrue(user.check_password("Distinct-Viewer-Pass!482"));self.assertTrue(user.is_active);self.assertFalse(user.is_staff);self.assertFalse(user.is_superuser)
 def test_viewer_cannot_view_or_create_users(self):
  self.client.force_login(self.viewer)
  self.assertEqual(self.client.get("/telemetry/admin/auth/user/").status_code,302)
  self.assertEqual(self.client.post("/telemetry/admin/auth/user/add/",{"username":"intruder"}).status_code,302)
  self.assertFalse(get_user_model().objects.filter(username="intruder").exists())
 def test_anonymous_redirected_to_admin_login(self):
  self.assertEqual(self.client.get("/telemetry/admin/auth/user/").status_code,302)
 def test_admin_password_reset(self):
  self.client.force_login(self.admin)
  response=self.client.post(f"/telemetry/admin/auth/user/{self.viewer.pk}/password/",{"password1":"Changed-Viewer-Pass!482","password2":"Changed-Viewer-Pass!482"})
  self.assertEqual(response.status_code,302);self.viewer.refresh_from_db();self.assertTrue(self.viewer.check_password("Changed-Viewer-Pass!482"))
 def test_deactivated_account_session_cannot_access_dashboard(self):
  self.client.force_login(self.viewer);self.viewer.is_active=False;self.viewer.save()
  self.assertEqual(self.client.get("/telemetry/").status_code,302)
 def test_admin_post_requires_csrf(self):
  client=Client(enforce_csrf_checks=True);client.force_login(self.admin)
  self.assertEqual(client.post("/telemetry/admin/auth/user/add/",{"username":"no-csrf"}).status_code,403)


class MerakiViewTests(SimpleTestCase):
 @patch("inventory.data.Path.read_text",side_effect=OSError)
 def test_cloud_devices_do_not_get_fake_cpu_fan_or_power_checks(self,_):
  device=sample();device["meraki_integration_id"]=1;device["device_role"]="sensor"
  self.assertEqual([x["resource"] for x in data.health(device)],["sensor-freshness","temperature","battery"])
  device["device_role"]="access-point"
  self.assertEqual([x["resource"] for x in data.health(device)],["availability"])
 def test_cloud_freshness_uses_cloud_collection_not_ssh_state(self):
  device=sample();device.update(meraki_integration_id=1,meraki_collected_at=datetime.now(timezone.utc))
  self.assertFalse(data.attach_alerts([device],[])[0]["telemetry_stale"])
  device["meraki_collected_at"]=datetime.now(timezone.utc)-timedelta(hours=1)
  self.assertTrue(data.attach_alerts([device],[])[0]["telemetry_stale"])


class CategoryTests(TestCase):
 def setUp(self):
  self.user=get_user_model().objects.create_user(username="categories")
  self.client.force_login(self.user)
 @patch("inventory.views.data.integration_health",return_value=[])
 @patch("inventory.views.data.alert_rows",return_value=[])
 @patch("inventory.views.data.devices")
 def test_categories_and_location_drilldown(self,devices,*_):
  local=sample()
  cloud=dict(sample(),id=2,hostname="meraki-serial",meraki_integration_id=1,display_name="Cloud AP")
  devices.side_effect=lambda:[dict(local),dict(cloud)]
  home=self.client.get("/telemetry/")
  self.assertContains(home,"CP Locations");self.assertContains(home,"View devices")
  self.assertNotContains(home,"Cloud AP");self.assertNotContains(home,"CHC-SW-01-01")
  self.assertContains(self.client.get("/telemetry/?location=Canton"),"CHC-SW-01-01")
  meraki=self.client.get("/telemetry/meraki/?location=Canton")
  self.assertContains(meraki,"Cloud AP");self.assertNotContains(meraki,"CHC-SW-01-01")
 def test_aliases_distinguish_same_model_and_preserve_alert_join(self):
  devices=[dict(sample(),hostname="serial-b",meraki_integration_id=1,model="MR45",location_name="Testtown"),dict(sample(),hostname="serial-a",meraki_integration_id=1,model="MR45",location_name="Testtown")]
  data.name_meraki_devices(devices)
  self.assertEqual(devices[1]["monitoring_name"],"meraki-testtown-mr45-01")
  result=data.attach_alerts(devices,[dict(alert(),hostname="meraki-testtown-mr45-01")])
  self.assertEqual(result[1]["alert_status"],"CRITICAL")

 def test_new_device_cannot_take_pinned_pilot_name(self):
  devices=[dict(sample(),hostname="meraki-884814-q3aa-2hjm-paye",meraki_integration_id=1,model="MR45",location_name="Ogdensburg"),dict(sample(),hostname="earlier-new-device",meraki_integration_id=1,model="MR45",location_name="Ogdensburg")]
  data.name_meraki_devices(devices)
  self.assertEqual(devices[0]["monitoring_name"],"meraki-ogdensburg-mr45-01")
  self.assertEqual(devices[1]["monitoring_name"],"meraki-ogdensburg-mr45-09")


class MrViewTests(SimpleTestCase):
 @patch('inventory.data.Path.read_text',side_effect=OSError)
 def test_mr_only_gets_supported_device_health(self,_):
  d=sample();d.update(meraki_integration_id=1,model='MR45')
  self.assertEqual([r['resource'] for r in data.health(d)],['availability','cpu-load','cpu-load-estimate','memory','power-mode','uplink'])
  d['model']='MX68W';self.assertEqual([r['resource'] for r in data.health(d)],['availability'])

class MerakiDisplayNameTests(SimpleTestCase):
 def test_cloud_name_is_primary_label_without_changing_monitoring_identity(self):
  from django.template.loader import render_to_string
  d=sample()
  d.update(display_name='CHC-AP-02-01 - Back Right',monitoring_name='meraki-malone-mr45-01',meraki_integration_id=1,alert_status='OK')
  overview=render_to_string('inventory/overview.html',{'groups':{'Malone':[d]},'category':'meraki'})
  detail=render_to_string('inventory/device.html',{'device':d})
  self.assertIn('<h3>CHC-AP-02-01 - Back Right</h3>',overview)
  self.assertIn('<h1>CHC-AP-02-01 - Back Right</h1>',detail)
  self.assertEqual(d['monitoring_name'],'meraki-malone-mr45-01')
  a=dict(alert(),hostname=d['monitoring_name'])
  self.assertEqual(data.attach_alerts([d],[a])[0]['alert_status'],'CRITICAL')
 def test_missing_cloud_name_falls_back_to_hostname(self):
  from django.template.loader import render_to_string
  d=sample()
  self.assertIn('<h1>CHC-SW-01-01</h1>',render_to_string('inventory/device.html',{'device':d}))

class CpuCalibrationTests(SimpleTestCase):
 @patch('inventory.management.commands.cpu_calibration.devices')
 @patch('inventory.management.commands.cpu_calibration.rows')
 def test_archive_deduplicates_and_pairs_only_exact_times(self, mock_rows, mock_devices):
  import tempfile,sqlite3,json,io
  from pathlib import Path
  from django.core.management import call_command,CommandError
  observed=datetime.now(timezone.utc).isoformat()
  mock_devices.return_value=[{'meraki_integration_id':1,'meraki_serial':'SERIAL','model':'MR45','display_name':'AP'}]
  payload={'collected_at':observed,'mr_observations':[{'serial':'SERIAL','observed_at':observed,'cpu_load5':2000,'cpu_count':4}]}
  mock_rows.return_value=[{'integration_id':1,'snapshot_json':json.dumps({'payload':payload})}]
  with tempfile.TemporaryDirectory() as folder:
   db=Path(folder)/'samples.sqlite3';output=io.StringIO()
   for _ in range(2):call_command('cpu_calibration',database=str(db),stdout=output)
   with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM samples').fetchone()[0],1)
   csv=Path(folder)/'ui.csv'
   csv.write_text('integration_id,serial,observed_at,dashboard_value,unit,provenance\n1,SERIAL,'+observed+',50,percent,tooltip\n')
   call_command('cpu_calibration',database=str(db),dashboard_csv=str(csv),stdout=output)
   self.assertIn('median absolute error=0.0000',output.getvalue())
   csv.write_text('integration_id,serial,observed_at,dashboard_value,unit,provenance\n1,SERIAL,2000-01-01T00:00:00Z,50,percent,tooltip\n')
   with self.assertRaises(CommandError):call_command('cpu_calibration',database=str(db),dashboard_csv=str(csv),stdout=io.StringIO())
   payload['mr_observations'][0]['observed_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
   mock_rows.return_value=[{'integration_id':1,'snapshot_json':json.dumps({'payload':payload})}]
   call_command('cpu_calibration',database=str(db),stdout=io.StringIO())
   with sqlite3.connect(db) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM samples').fetchone()[0],1)

class CpuHistoryTests(SimpleTestCase):
 def test_history_is_scoped_preserves_over_100_and_handles_missing_archive(self):
  import sqlite3,tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'samples.sqlite3'
   with self.settings(CPU_CALIBRATION_DATABASE=str(path)):
    d=dict(meraki_integration_id=1,meraki_serial='SERIAL',model='MR45')
    self.assertTrue(data.estimated_cpu_history(d)['unavailable'])
    self.assertFalse(path.exists())
    with sqlite3.connect(path) as db:
     db.execute('CREATE TABLE samples (integration INTEGER,serial TEXT,observed_at TEXT,cpu_load5 INTEGER,cpu_count INTEGER)')
     db.execute('INSERT INTO samples VALUES (?,?,?,?,?)',(1,'SERIAL',(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat(),500000,4))
     db.execute('INSERT INTO samples VALUES (?,?,?,?,?)',(2,'SERIAL',datetime.now(timezone.utc).isoformat(),1000000,4))
    result=data.estimated_cpu_history(d)
    self.assertEqual(result['count'],1);self.assertEqual(result['maximum'],125)
    self.assertEqual(len(result['segments']),1)


class SensorSuppressionTests(SimpleTestCase):
 def test_suppressed_sensor_checks_are_explicitly_labeled(self):
  from django.template.loader import render_to_string
  d=sample();d['meraki_integration_id']=1
  d['alerts']=[dict(alert('OK'),suppressed=True)]
  html=render_to_string('inventory/device.html',{'device':d,'health':[dict(resource='temperature',status='OK',suppressed=True,message='SUPPRESSED: battery 0%')]})
  self.assertGreaterEqual(html.count('SUPPRESSED</span>'),2)
  self.assertIn('SUPPRESSED · not evaluated',html)

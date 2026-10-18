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

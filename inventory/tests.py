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
  self.user=get_user_model().objects.create_user(username="operator",password="password-test")
 def test_login_required_for_inventory(self):
  self.assertEqual(self.client.get("/telemetry/").status_code,302);self.assertEqual(self.client.get("/telemetry/devices/1/").status_code,302)
 def test_healthcheck_does_not_disclose_inventory(self):
  self.assertEqual(self.client.get("/telemetry/healthz/").json()["status"],"ok")
 @patch("inventory.views.data.alert_rows",return_value=[alert()])
 @patch("inventory.views.data.devices",side_effect=lambda:[sample()])
 def test_location_card_and_filters(self,devices,alerts):
  self.client.force_login(self.user)
  response=self.client.get("/telemetry/");self.assertContains(response,"Canton");self.assertContains(response,"CRITICAL");self.assertContains(response,"CHC-SW-01-01")
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

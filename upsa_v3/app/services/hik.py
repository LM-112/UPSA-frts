"""
Hikvision ISAPI client for DS-K1T323MBFWX-E1 MinMoe terminal.
Simulate=True mode returns canned responses for demo without the device on the desk.
"""
from __future__ import annotations
import json, logging, requests
from requests.auth import HTTPDigestAuth

log = logging.getLogger(__name__)


class HikvisionTerminal:
    MODEL = "DS-K1T323MBFWX-E1"

    def __init__(self, host, port=80, username="admin", password="", timeout=10, simulate=False):
        self.host, self.port = host, port
        self.auth = HTTPDigestAuth(username, password)
        self.timeout = timeout
        self.simulate = simulate
        self.base = f"http://{host}:{port}"

    def _req(self, method, path, **kw):
        return requests.request(method, self.base + path, auth=self.auth,
                                timeout=self.timeout, **kw)

    def get_device_info(self):
        if self.simulate:
            return {"deviceName": f"{self.MODEL} (simulated)", "model": self.MODEL,
                    "serialNumber": "GM6647437", "firmwareVersion": "V4.3.0 build 240301",
                    "macAddress": "AA:BB:CC:DD:EE:FF"}
        try:
            r = self._req("GET", "/ISAPI/System/deviceInfo")
            if r.status_code != 200:
                return None
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.text)
            ns = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
            def tx(tag):
                el = root.find(f"{{{ns}}}{tag}" if ns else tag)
                return el.text if el is not None else ""
            return {"deviceName": tx("deviceName"), "model": tx("model"),
                    "serialNumber": tx("serialNumber"), "firmwareVersion": tx("firmwareVersion"),
                    "macAddress": tx("macAddress")}
        except Exception as e:
            log.warning("Hik unreachable: %s", e)
            return None

    def add_person(self, employee_id, name, gender="male"):
        if self.simulate:
            return True, f"[sim] added {employee_id}"
        body = {"UserInfo": {"employeeNo": str(employee_id), "name": name,
                             "userType": "normal", "gender": gender,
                             "Valid": {"enable": True, "beginTime": "2020-01-01T00:00:00",
                                       "endTime": "2030-12-31T23:59:59"},
                             "doorRight": "1"}}
        try:
            r = self._req("POST", "/ISAPI/AccessControl/UserInfo/Record?format=json",
                          json=body)
            return r.status_code in (200, 201), r.text
        except Exception as e:
            return False, str(e)

    def add_face_picture(self, employee_id, image_bytes):
        if self.simulate:
            return True, f"[sim] face uploaded for {employee_id}"
        meta = {"faceLibType": "blackFD", "FDID": "1", "FPID": str(employee_id)}
        try:
            r = self._req("POST", "/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json",
                          files={"FaceDataRecord": (None, json.dumps(meta), "application/json"),
                                 "img": (f"{employee_id}.jpg", image_bytes, "image/jpeg")})
            return r.status_code in (200, 201), r.text
        except Exception as e:
            return False, str(e)

    def delete_person(self, employee_id):
        if self.simulate:
            return True, f"[sim] deleted {employee_id}"
        body = {"UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": str(employee_id)}]}}
        try:
            r = self._req("PUT", "/ISAPI/AccessControl/UserInfo/Delete?format=json", json=body)
            return r.status_code == 200, r.text
        except Exception as e:
            return False, str(e)

    def register_event_listener(self, listener_url):
        if self.simulate:
            return True, f"[sim] listener registered at {listener_url}"
        body = {"HttpHostNotification": {"id": "1", "url": listener_url,
                                         "protocolType": "HTTP", "parameterFormatType": "JSON",
                                         "httpAuthenticationMethod": "none"}}
        try:
            r = self._req("PUT", "/ISAPI/Event/notification/httpHosts/1?format=json", json=body)
            return r.status_code == 200, r.text
        except Exception as e:
            return False, str(e)

"""
Sistema de Gestão Hospitalar - Authentication Script
Session-based with signup
"""
import requests
import json
from mitmproxy import ctx

class GestaoHospitalarAuth:
    def __init__(self):
        self.token = None
        self.base_url = "http://localhost:8080"
    
    def get_token(self):
        if self.token is None:
            try:
                # Register
                signup_url = f"{self.base_url}/register"
                signup_payload = {
                    "email": "restapitestteam@gmail.com",
                    "password": "universe",
                    "phone": "+39 3406089282",
                    "address": "Test Address",
                    "name": "REST API Test Team"
                }
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
                
                signup_response = requests.post(signup_url, json=signup_payload, headers=headers, timeout=5)
                
                if signup_response.status_code in [200, 201]:
                    # Get session cookie
                    if "JSESSIONID" in signup_response.cookies:
                        self.token = signup_response.cookies.get("JSESSIONID")
                        ctx.log.info(f"[Gestao Hospitalar Auth] Session obtained")
                else:
                    ctx.log.warn(f"[Gestao Hospitalar Auth] Signup failed: {signup_response.status_code}")
            except Exception as e:
                ctx.log.error(f"[Gestao Hospitalar Auth] Error: {e}")
        
        return self.token
    
    def request(self, flow):
        # Skip register endpoint
        if "/register" in flow.request.pretty_url:
            return
        
        token = self.get_token()
        if token:
            flow.request.headers["Cookie"] = f"JSESSIONID={token}"

addons = [GestaoHospitalarAuth()]

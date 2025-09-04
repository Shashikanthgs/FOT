from urllib import response
import pandas as pd
import requests

class DhanClient:
    def __init__(self, client_id, access_token, instruments = None, base_url="https://api.dhan.co/v2"):
        self.client_id = client_id
        self.access_token = access_token
        self.base_url = base_url
        if instruments is not None:
            self.instruments_df = instruments
        else:
            import os
            csv_path = os.path.join(os.path.dirname(__file__), 'Dependencies', 'my_instruments.csv')
            try:
                self.instruments_df = pd.read_csv(csv_path)
            except FileNotFoundError:
                raise FileNotFoundError(f"The file '{csv_path}' was not found. Please check the path and ensure the file exists.")

    def fetch_expiry_list(self, underlying_scrip, underlying_seg):
        url = f"{self.base_url}/optionchain/expirylist"
        headers = {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
        }
        payload = {
            "UnderlyingScrip": underlying_scrip,
            "UnderlyingSeg": underlying_seg
        }
        response = requests.post(url, headers=headers, json=payload)
        return self.handle_post_response(response)        

    def fetch_option_chain(self, underlying_scrip, underlying_seg, expiry):
        url = f"{self.base_url}/optionchain"
        headers = {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
            }
        payload = {
            "UnderlyingScrip": underlying_scrip,
            "UnderlyingSeg": underlying_seg,
            "Expiry": expiry
        }
        response = requests.post(url, headers=headers, json=payload)
        return self.handle_post_response(response)

    def handle_post_response(self, response):
        """Handles the response from a POST request."""
        if response.status_code != 200:
            raise Exception(f"POST request failed with status code {response.status_code}: {response.text}")
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            raise Exception(f"POST request failed: {err} - {response.text}")
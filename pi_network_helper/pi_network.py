# pi_network/pi_network.py

import json
import requests
import stellar_sdk as s_sdk


class PiNetwork:
    def __init__(self):
        self.api_key = ""
        self.client = None
        self.account = None
        self.base_url = "https://api.minepi.com"
        self.open_payments = {}
        self.network = ""
        self.server = None
        self.keypair = None
        self.fee = 0

    def initialize(self, api_key: str, wallet_private_key: str, network: str) -> bool:
        if not self.validate_private_seed_format(wallet_private_key):
            print("No valid private seed!")
            return False

        self.api_key = api_key
        self.load_account(wallet_private_key, network)
        self.fee = self.server.fetch_base_fee()
        return True

    def get_balance(self) -> float:
        try:
            balances = self.server.accounts().account_id(self.keypair.public_key).call()["balances"]
            for balance in balances:
                if balance["asset_type"] == "native":
                    return float(balance["balance"])
            return 0.0
        except Exception as e:
            print(e)
            return 0.0

    def get_payment(self, payment_id: str) -> dict:
        url = f"{self.base_url}/v2/payments/{payment_id}"
        response = requests.get(url, headers=self.get_http_headers(), timeout=500)
        return self.handle_http_response(response)

    def create_payment(self, payment_data: dict) -> str:
        if not self.validate_payment_data(payment_data):
            print("No valid payments found. Creating a new one...")
            return ""

        balance = self.get_balance()
        payment_amount = float(payment_data["amount"])
        if (payment_amount + (self.fee / 10000000)) > balance:
            return ""

        response = requests.post(
            f"{self.base_url}/v2/payments",
            json={"payment": payment_data},
            headers=self.get_http_headers(),
            timeout=500
        )
        parsed_response = self.handle_http_response(response)
        identifier = parsed_response.get("identifier")
        if identifier:
            self.open_payments[identifier] = parsed_response
        return identifier

    def submit_payment(self, payment_id: str, pending_payment: dict = None) -> str:
        if payment_id not in self.open_payments:
            return False

        payment = pending_payment if pending_payment else self.open_payments[payment_id]
        balance = self.get_balance()
        payment_amount = float(payment["amount"])
        if (payment_amount + (self.fee / 10000000)) > balance:
            return ""

        transaction = self.build_a2u_transaction(payment)
        txid = self.submit_transaction(transaction)
        self.open_payments.pop(payment_id, None)
        return txid

    def approved_payment(self, identifier: str) -> dict:
        url = f"{self.base_url}/v2/payments/{identifier}/approve"
        response = requests.post(url, headers=self.get_http_headers(), timeout=500)
        return self.handle_http_response(response)

    def complete_payment(self, identifier: str, txid: str) -> dict:
        obj = {"txid": txid} if txid else {}
        url = f"{self.base_url}/v2/payments/{identifier}/complete"
        response = requests.post(url, json=obj, headers=self.get_http_headers(), timeout=500)
        return self.handle_http_response(response)

    def cancel_payment(self, identifier: str) -> dict:
        url = f"{self.base_url}/v2/payments/{identifier}/cancel"
        response = requests.post(url, headers=self.get_http_headers(), timeout=500)
        return self.handle_http_response(response)

    def get_incomplete_server_payments(self) -> list:
        url = f"{self.base_url}/v2/payments/incomplete_server_payments"
        response = requests.get(url, headers=self.get_http_headers(), timeout=500)
        return self.handle_http_response(response).get("incomplete_server_payments", [])

    def get_http_headers(self) -> dict:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

    def handle_http_response(self, response) -> dict:
        try:
            result = response.json()
            return result
        except Exception as e:
            print(e)
            return False

    def load_account(self, private_seed: str, network: str):
        self.keypair = s_sdk.Keypair.from_secret(private_seed)
        horizon = "https://api.mainnet.minepi.com" if network == "Pi Network" else "https://api.testnet.minepi.com"
        self.server = s_sdk.Server(horizon)
        self.account = self.server.load_account(self.keypair.public_key)

    def build_a2u_transaction(self, transaction_data: dict):
        if not self.validate_payment_data(transaction_data):
            print("No valid transaction!")
            return None

        transaction = (
            s_sdk.TransactionBuilder(
                source_account=self.account,
                network_passphrase=self.network,
                base_fee=self.fee,
            )
            .add_text_memo(transaction_data["identifier"])
            .append_payment_op(transaction_data["to_address"], s_sdk.Asset.native(), str(transaction_data["amount"]))
            .set_timeout(30)
            .build()
        )
        return transaction

    def submit_transaction(self, transaction) -> str:
        transaction.sign(self.keypair)
        response = self.server.submit_transaction(transaction)
        return response["id"]

    def validate_payment_data(self, data: dict) -> bool:
        required_keys = ["amount", "memo", "metadata", "uid", "identifier", "recipient"]
        return all(key in data for key in required_keys)

    def validate_private_seed_format(self, seed: str) -> bool:
        return seed.upper().startswith("S") and len(seed) == 56

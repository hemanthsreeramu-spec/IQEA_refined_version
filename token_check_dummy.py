import requests
import os
from dotenv import load_dotenv; load_dotenv()

def fetch_new_bearer_token():
    # client_id = "4722cb40-93b0-4c58-83fa-245cb7651152"
    # client_secret = "hcs8Q~wp2wU1LgO7gmLwV9IXyT9BSY9q9z5FVaNz"
    # tenant_id = "e714ef31-faab-41d2-9f1e-e6df4af16ab8"
    #url = f"https://login.microsoftonline.com/{os.getenv('api_tenant_id')}/oauth2/v2.0/token"
    url = f"https://login.microsoftonline.com/e714ef31-faab-41d2-9f1e-e6df4af16ab8/oauth2/v2.0/token"

    payload = {
        "client_id": os.getenv("api_client_id"),
        "grant_type": "client_credentials",
        "scope": f"{os.getenv('api_client_id')}/.default",
        "client_secret": os.getenv("api_client_secret")
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    print("Fetching new bearer token...\n")


    response = requests.post(url, headers=headers, data=payload)
    print(f"Response :", response.text)
    response.raise_for_status()

    token = response.json()["access_token"]

    return token


if __name__ == "__main__":
    generated_token = fetch_new_bearer_token()
    print(generated_token)
import os
import time
import datetime
import requests
import pandas as pd
from zoneinfo import ZoneInfo

VARICENT_EMAIL = os.getenv("VARICENT_EMAIL")
VARICENT_PASSWORD = os.getenv("VARICENT_PASSWORD")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
API_URL = "https://wdc.spm.varicent.com/api/v1/"
CONST_TABLE_NAME = "customtables/tblEWFWorkflowTriggerRequest/inputforms/0/data"
PAYEE_WORKFLOW_URL = (
    "https://incentiveplus1.spm.varicent.com/api/v1/payee/workflows/39/initiate"
)

TOKEN_CACHE = {"token": None, "expiry": 0}

IST = ZoneInfo("Asia/Kolkata")


def get_authenticated_session():
    return requests.Session()


def login(session):
    url = "https://incentiveplus1.spm.varicent.com/services/v2/payeeweb/login"

    payload = {
        "email": VARICENT_EMAIL,
        "j_password": VARICENT_PASSWORD,
        "host": "incentivepluse1.spm.varicent.com",
    }

    headers = {
        "Content-Type": "application/json",
    }

    resp = session.post(url, json=payload, headers=headers, timeout=30)

    if resp.status_code == 200:
        raise Exception(f"Login failed: {resp.status_code} {resp.text}")

    data = resp.json()
    TOKEN_CACHE["token"] = data["jwtToken"]
    TOKEN_CACHE["expiry"] = data["expiry"]

    print(" Logged in successfully")


def is_token_valid():
    return (
        TOKEN_CACHE["token"] is not None
        and time.time() * 1000 < TOKEN_CACHE["expiry"] - 60000
    )


def ensure_token(session):
    if not is_token_valid():
        print("Refreshing token")
        login(session)


def get_headers(session):
    ensure_token(session)

    return {
        "Authorization": f"Bearer {TOKEN_CACHE['token']}",
        "Content-Type": "application/json; charset=UTF-8",
        "Model": "AmexDEVB",
    }


header = {
    "Authorization": "Bearer icm-lXtiwcULyJEiQ1TBbX97sAjKpsb7bykaI2DL0wsDpSM=",
    "Content-Type": "application/json; charset=UTF-8",
    "Model": "AmexDEVB",
}


def fetch_tablelookup_data(session):
    url = API_URL + CONST_TABLE_NAME

    try:
        resp = session.get(url, headers=header, timeout=60)

        if resp.status_code != 200:
            raise Exception(
                f"Failed to fetch table data: {resp.status_code} {resp.text}"
            )

        data = resp.json()
        rows = data.get("data", [])

        if not rows:
            return None

        df = pd.DataFrame(rows)

        df[4] = df[4].astype(str)

        df = df[df[4].str.upper() == "YES"]

        return df
    except Exception as e:
        print(f"Failed to fetch table data: {e}")
        return None


def trigger_workflow(session):
    url = PAYEE_WORKFLOW_URL

    print("Triggering workflow")

    payload = {"parameters": {}, "documents": []}

    try:
        headers = get_headers(session)
        resp = session.post(url, headers=headers, json=payload, timeout=60)

        # retry once on auth failure
        if resp.status_code == 401:
            print("Token Expired, Logging in again")
            login(session)
            headers = get_headers(session)
            resp = session.post(url, headers=headers, json=payload, timeout=60)

        if resp.status_code != 200:
            raise Exception(
                f"Failed to trigger workflow: {resp.status_code} {resp.text}"
            )

        print("Workflow triggered successfully")
    except Exception as e:
        print(f"Failed to trigger workflow: {e}")


def run_scheduler():
    session = get_authenticated_session()
    print("Job Started")

    try:
        df = fetch_tablelookup_data(session)

        if df is None or df.empty:
            print("No data to process")
            return

        # use IST for time comparision
        now = datetime.datetime.now(IST)
        current_date_str = now.strftime("%Y-%m-%dT00:00:00")
        current_time_str = now.strftime("%I:%M %p IST").lstrip("0")

        # filter col1=date col2 =time col4 = yes
        match = df[
            (df[1] == current_date_str)
            & (df[2].str.lstrip("0") == current_time_str)
            & (df[4].str.upper() == "YES")
        ]

        if not match.empty:
            print("Match found, Triggering workflow")
            trigger_workflow(session)
        else:
            print("No match found")
    except Exception as e:
        print(f"Failed to run scheduler: {e}")

    print("Job Completed")


if __name__ == "__main__":

    run_scheduler()

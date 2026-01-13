# add_to_search_ enter role id
import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

#when running locally use this command: streamlit run main.py --server.port 8502

## Setup states
#
# Current table
if "table" not in st.session_state:
    st.session_state.table = pd.DataFrame()
#
#  State, which table to display below header
if "step" not in st.session_state:
    st.session_state.step = 0  # 0: initial state, 1: has been through rocket reach, 2: ready to send to hubspot

st.set_page_config(page_title="Hubspot Bulk Upload", page_icon="📤", layout="wide")

# show title
st.title("(P)ython (S)ourcing utility by (G)abe")
st.markdown("*PSG for short*")

if st.session_state.step == 0:
    # Check if user is already authenticated
    if st.user.is_logged_in:
        # User is authenticated, move to next step
        st.session_state.step = 1
        st.rerun()
    else:
        # Show login button
        if st.button("Login With Work Account"):
            st.login()


# upload file
elif st.session_state.step == 1:
    print(st.user.email)
    st.header("Step 1: Import from Linkedin Recruiter")
    st.subheader("*Hint you can edit any of this data in the grid below")
    file = st.file_uploader("Upload Linkedin CSV Export", type="csv")
    if file:
        st.session_state.table = pd.read_csv(file)
        # display first table
        st.data_editor(st.session_state.table, width="content")

        # send to n8n workflow
        if st.button("🚀 Enrich Emails with RocketReach"):
            st.info(
                "Enriching with RocketReach please wait",
                icon="spinner",
                width="stretch",
            )
            data1 = st.session_state.table.to_json(orient="records")
            rocketInrich = requests.post(
                "https://revelone.app.n8n.cloud/webhook/d038ef22-7924-4b5c-a7bd-d5bc2bacd5f0",
                json=data1,
                headers={"Content-Type": "application/json"},
            )

            print(rocketInrich.content)
            st.session_state.table = pd.DataFrame(rocketInrich.json())
            st.session_state.step += 1
            st.rerun()

#create contacts
elif st.session_state.step == 2:
    # header and subheader
    st.header("Step 2: Create contacts in HubSpot")
    st.subheader("hint you can edit any of this data")

    # show current table
    st.data_editor(st.session_state.table, width="content")

    # send data to n8n
    if st.button("Create contacts in HubSpot"):
        st.info(
            "Creating contacts in Hubspot please wait", icon="spinner", width="stretch"
        )
        data2 = st.session_state.table.to_json(orient="records")
        hubspotData = requests.post(
            "https://revelone.app.n8n.cloud/webhook/9ddc6dd0-d758-4b17-8ff0-efe8988e577f",
            json={
                "user": st.user.email,
                "contacts": data2,
            },
            headers={"Content-Type": "application/json"},
        )  ## this is the devolpment url remember to switch to prod

        print(hubspotData.content)
        st.session_state.table = pd.DataFrame(hubspotData.json())
        st.session_state.step += 1
        st.rerun()

elif st.session_state.step == 3:
    st.header("Step 3: Create Candidate trackers")
    st.subheader("Found or Created contacts in HubSpot")
    st.write("'🔍 ' means they were already in hubspot '✅' means they were created")
    # show current table
    st.data_editor(st.session_state.table, width="content")

    # Get active searches
    searches = requests.post(
        url="https://api.hubapi.com/crm/v3/objects/2-30586852/search",
        headers={
            "Authorization": os.getenv("hubspotPat"),
            "Content-Type": "application/json",
        },
        json={
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "search_outcome",
                            "operator": "EQ",
                            "value": "0. Active",
                        }
                    ]
                }
            ],
            "properties": ["role_name", "role_id"],
            "limit": 100,
        },
    )

    result = searches.json()
    searches_dict = {
        search["properties"]["role_name"]: search["id"]
        for search in result.get("results", [])
    }
    # select which search to add candidate to
    selected_search = st.selectbox(
        "Add to which search (type to search)", list(searches_dict.keys()), index=None
    )

    if selected_search is not None:
        if st.button(f"Add to search: {selected_search}"):
            st.info(
                "Associating with search, please wait", icon="spinner", width="stretch"
            )
            trackerData = requests.post(
                "https://revelone.app.n8n.cloud/webhook/389f2b39-2c32-43ee-8ad7-cfc34def0980",
                json={
                    "search_id": searches_dict[selected_search],
                    "candidates": st.session_state.table.to_json(orient="records"),
                },
                headers={"Content-Type": "application/json"},
            )
            st.session_state.table = pd.DataFrame(trackerData.json())
            st.session_state.step += 1
            st.rerun()

elif st.session_state.step == 4:
    st.success("Trackers Created! ", icon="🎇", width="stretch")
    st.data_editor(st.session_state.table, width="content")

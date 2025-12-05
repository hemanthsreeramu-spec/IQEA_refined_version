import subprocess
from github import Github, GithubException  # Make sure GithubException is imported
from gitlab import Gitlab
import pandas as pd
import re
from github import Github
from pyasn1_modules.rfc8017 import emptyString
from selenium.webdriver.chrome.service import Service
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.wait import WebDriverWait
import os
import json
import shutil
import threading
import time
import utilities.Utilities_Xpath as utils
import utilities.utils_action as action_utils
import utilities.db_utils.handler as db_handler
import utilities.TMT_Connection.Test_management_tool_utils as tmt_utils
from PIL import Image
import pytesseract
import io
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from dotenv import load_dotenv; load_dotenv()
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

#setting details - source either file or database
from config.settings_reader import get_source, get_update_user,get_model
source = get_source()
model_type= get_model()

# Setup output folder
current_path = os.getcwd()
input_folder = os.path.join(current_path, "Input")
output_folder = os.path.join(current_path, "output")
Action_collection = os.path.join(output_folder, "Action_collection")
Page_collection = os.path.join(output_folder, "page_file_generator")
Test_case_collection = os.path.join(output_folder, "Test_Cases_collection")
Test_file_generator = os.path.join(output_folder, "test_file_generator")
feature_file_collection = os.path.join(output_folder, "Feature_file_generator")
test_data_folder=os.path.join(output_folder, "Test_data_generator")
api_template_file=os.path.join(input_folder,"Api_template.xlsx")
os.makedirs(Page_collection, exist_ok=True)
os.makedirs(Test_case_collection, exist_ok=True)
os.makedirs(Action_collection, exist_ok=True)
os.makedirs(feature_file_collection, exist_ok=True)
os.makedirs(test_data_folder, exist_ok=True)
#page_screenshot_folder_new = os.path.join(Action_collection, "page_screenshot_valid")
page_screenshot_folder = os.path.join(Action_collection, "Equifix")
os.makedirs(page_screenshot_folder, exist_ok=True)
os.makedirs(Test_file_generator, exist_ok=True)

st.set_page_config(
    page_title="TigerQE AI iQEA",
    page_icon="🤖",
    layout="centered"
)

# Session state setup

if "checkbox1_state" not in st.session_state:
    st.session_state.checkbox1_state = True
#### Api
if "api_data" not in st.session_state:
    st.session_state.api_data= ""
st.title(" 🤖 TigerQE AI Platform - 🔍 API Validator")
col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader(
        "Upload API Details Excel document",
        type=['xlsx'],
        key="api_uploader"
    )

with col2:
    st.markdown("### Template")
    with open(api_template_file, "rb") as f:
        st.download_button(
            label="⬇ Download Template",
            data=f,
            file_name="API_Test_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if uploaded_file:
   df = pd.read_excel(uploaded_file)
   st.success("API File Uploaded Successfully!")
   st.dataframe(df)

   if st.button("Validate APIs"):
       st.session_state.api_data = df
       st.success("API Data Loaded. Click 'Start Testing'")
   if st.session_state.api_data:
       if st.button("Start Testing"):
           st.write("Running API Tests...")
           st.session_state.api_data=utils.excel_to_api_list(st.session_state.api_data)
           results=utils.call_api(st.session_state.api_data)
           result_df = pd.DataFrame(results)
           st.dataframe(result_df)
   else:
       st.error("Please upload Api details excel file")
# Footer of webpage
st.divider()
st.markdown("""    
### Contact Us
- Reach us at [QE Core Team](mailto:sahil.gupta@tigeranalytics.com)
""")




